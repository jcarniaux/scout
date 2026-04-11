"""
GET /jobs and GET /jobs/{jobId} API handlers.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from shared.db import DynamoDBHelper
from shared.response import success_response, error_response, not_found_response, unauthorized_response
from shared.models import dynamo_deserialize

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()


def get_user_sub(event: Dict[str, Any]) -> Optional[str]:
    """Extract Cognito user sub from event."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def get_date_range_start(date_range: Optional[str]) -> str:
    """
    Convert date range param to a date-only ISO string (YYYY-MM-DD).

    The enrichment Lambda stores postedDate as date-only strings (e.g. "2026-04-11").
    The DateIndex range key comparison must use the same format — a full ISO datetime
    like "2026-04-11T00:00:00" is lexicographically GREATER than "2026-04-11", which
    would exclude jobs posted on the boundary date.
    """
    now = datetime.utcnow()

    if date_range == "24h":
        start = now - timedelta(hours=24)
    elif date_range == "7d":
        start = now - timedelta(days=7)
    elif date_range == "30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=30)  # Default 30 days

    return start.date().isoformat()


def serialize_job(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map raw DynamoDB field names to the camelCase shape the frontend expects,
    and sanitize sentinel strings ("nan", "None") that JobSpy emits for missing
    values — leaving them as None so JSON renders null rather than a string.
    """
    def clean(value: Any) -> Optional[Any]:
        if value is None:
            return None
        if isinstance(value, str) and value.lower() in ("nan", "none", ""):
            return None
        return value

    # pk is "JOB#{hash}" — strip the prefix to get the bare job ID
    pk = item.get("pk", "")
    job_id = pk[len("JOB#"):] if pk.startswith("JOB#") else pk

    return {
        "jobId":          job_id,
        "roleName":       clean(item.get("title")),
        "company":        clean(item.get("company")) or "Unknown",
        "location":       clean(item.get("location")) or "",
        "source":         item.get("source", ""),
        "sourceUrl":      clean(item.get("job_url")),
        "postedDate":     clean(item.get("postedDate") or item.get("date_posted")),
        "createdAt":      item.get("created_at") or item.get("crawled_at"),
        "description":    clean(item.get("description")),
        "jobType":        clean(item.get("job_type")),
        "salaryMin":      item.get("salary_min"),
        "salaryMax":      item.get("salary_max"),
        "glassdoorRating": item.get("rating"),
        "glassdoorUrl":   clean(item.get("glassdoor_url")),
        "benefits":       clean(item.get("benefits")),
        "ptoDays":        item.get("pto_days"),
        "sickDays":       item.get("sick_days"),
        "match401k":      clean(item.get("match_401k")),
        "applicationStatus": item.get("user_status", "NOT_APPLIED"),
        "notes":          clean(item.get("notes")),
    }


def filter_jobs(
    jobs: List[Dict[str, Any]],
    user_id: str,
    min_rating: Optional[float] = None,
    status_filter: Optional[str] = None,
    sort_by: str = "date",
) -> List[Dict[str, Any]]:
    """
    Filter and sort jobs.

    Args:
        jobs: List of job dicts
        user_id: User ID for status lookup
        min_rating: Minimum Glassdoor rating
        status_filter: Filter by application status
        sort_by: Sort field (date, salary, rating)

    Returns:
        Filtered and sorted job list
    """
    jobs_table = os.environ.get("USER_STATUS_TABLE")

    # Fetch user statuses if filtering by status
    user_statuses = {}
    if status_filter or jobs:
        try:
            items, _ = dynamodb.query(
                jobs_table,
                "pk = :pk",
                {":pk": user_id},
            )
            for item in items:
                job_id = item.get("sk", "").replace("JOB#", "")
                user_statuses[job_id] = item.get("status")
        except Exception as e:
            logger.warning(f"Error fetching user statuses: {e}")

    # Filter
    filtered = []
    for job in jobs:
        # Filter by rating
        if min_rating is not None and job.get("rating"):
            if float(job["rating"]) < min_rating:
                continue

        # Filter by status
        if status_filter:
            job_hash = job.get("job_hash")
            if user_statuses.get(job_hash) != status_filter:
                continue

        # Attach user status
        job_hash = job.get("job_hash")
        job["user_status"] = user_statuses.get(job_hash, "NOT_APPLIED")

        filtered.append(job)

    # Sort
    if sort_by == "salary" and all(job.get("salary_min") for job in filtered):
        filtered.sort(key=lambda x: x.get("salary_min", 0) or 0, reverse=True)
    elif sort_by == "rating" and any(job.get("rating") for job in filtered):
        filtered.sort(key=lambda x: x.get("rating", 0) or 0, reverse=True)
    else:
        # Default: sort by date
        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return filtered


def get_single_job(
    event: Dict[str, Any], context: Any
) -> Dict[str, Any]:
    """Handler for GET /jobs/{jobId}"""
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    jobs_table = os.environ.get("JOBS_TABLE")
    user_status_table = os.environ.get("USER_STATUS_TABLE")

    if not jobs_table or not user_status_table:
        return error_response("Missing environment variables", 500)

    # Get jobId from path parameters
    job_id = event.get("pathParameters", {}).get("jobId")
    if not job_id:
        return error_response("Missing jobId parameter", 400)

    try:
        # Query job by pk = "JOB#{job_hash}" — no separate GSI needed
        items, _ = dynamodb.query(
            jobs_table,
            "pk = :pk",
            {":pk": f"JOB#{job_id}"},
        )

        if not items:
            return not_found_response("Job not found")

        job = dynamo_deserialize(items[0])

        # Get user's status for this job
        user_status_key = {
            "pk": f"USER#{user_sub}",
            "sk": f"JOB#{job_id}",
        }
        status_item = dynamodb.get_item(user_status_table, user_status_key)
        job["user_status"] = status_item.get("status", "NOT_APPLIED") if status_item else "NOT_APPLIED"

        return success_response(serialize_job(job))

    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}", exc_info=True)
        return error_response("Error fetching job", 500)


def list_jobs(
    event: Dict[str, Any], context: Any
) -> Dict[str, Any]:
    """Handler for GET /jobs with filtering and pagination"""
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    jobs_table = os.environ.get("JOBS_TABLE")
    if not jobs_table:
        return error_response("Missing environment variables", 500)

    try:
        # Parse query parameters
        query_params = event.get("queryStringParameters", {}) or {}
        date_range = query_params.get("dateRange", "30d")
        min_rating = query_params.get("minRating")
        status_filter = query_params.get("status")
        sort_by = query_params.get("sort", "date")
        page = int(query_params.get("page", "1"))
        page_size = int(query_params.get("pageSize", "20"))

        if min_rating:
            min_rating = float(min_rating)

        # Calculate offset
        offset = (page - 1) * page_size

        # Query jobs by date
        start_date = get_date_range_start(date_range)

        # DateIndex: hash_key=gsi1pk ("JOB"), range_key=postedDate
        # All jobs share gsi1pk="JOB" so we can query the full date range.
        # Paginate through the FULL result set so the total count is accurate.
        # At Scout's scale (hundreds of jobs, not millions) this is fine.
        all_items: list = []
        last_key = None
        while True:
            items, last_key = dynamodb.query(
                jobs_table,
                "gsi1pk = :pk AND postedDate >= :start",
                {":pk": "JOB", ":start": start_date},
                index_name="DateIndex",
                scan_index_forward=False,
                exclusive_start_key=last_key,
            )
            all_items.extend(items)
            if not last_key:
                break

        # Deserialize, filter, then map to frontend shape
        jobs = [dynamo_deserialize(item) for item in all_items]
        filtered_jobs = filter_jobs(
            jobs,
            f"USER#{user_sub}",
            min_rating=min_rating,
            status_filter=status_filter,
            sort_by=sort_by,
        )

        # Paginate and serialize to frontend camelCase shape
        paginated_jobs = [serialize_job(j) for j in filtered_jobs[offset : offset + page_size]]

        return success_response({
            "jobs": paginated_jobs,
            "total": len(filtered_jobs),
            "page": page,
            "pageSize": page_size,
            "hasMore": len(filtered_jobs) > offset + page_size,
        })

    except ValueError as e:
        return error_response(f"Invalid parameter: {e}", 400)
    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        return error_response("Error fetching jobs", 500)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler dispatcher"""
    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("jobId")

    if job_id:
        return get_single_job(event, context)
    else:
        return list_jobs(event, context)
