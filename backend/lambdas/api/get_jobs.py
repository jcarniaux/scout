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
    """Convert date range param to ISO datetime string."""
    now = datetime.utcnow()

    if date_range == "24h":
        start = now - timedelta(hours=24)
    elif date_range == "7d":
        start = now - timedelta(days=7)
    elif date_range == "30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=30)  # Default 30 days

    return start.isoformat()


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
                "PK = :pk",
                {":pk": user_id},
            )
            for item in items:
                job_id = item.get("SK", "").replace("JOB#", "")
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
        # Query job by hash
        items, _ = dynamodb.query(
            jobs_table,
            "job_hash = :hash",
            {":hash": job_id},
            index_name="JobHashIndex",
        )

        if not items:
            return not_found_response("Job not found")

        job = dynamo_deserialize(items[0])

        # Get user's status for this job
        user_status_key = {
            "PK": f"USER#{user_sub}",
            "SK": f"JOB#{job_id}",
        }
        status_item = dynamodb.get_item(user_status_table, user_status_key)
        if status_item:
            job["user_status"] = status_item.get("status", "NOT_APPLIED")
        else:
            job["user_status"] = "NOT_APPLIED"

        return success_response(job)

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

        items, last_key = dynamodb.query(
            jobs_table,
            "created_at >= :start",
            {":start": start_date},
            index_name="DateIndex",
            limit=offset + page_size + 10,  # Fetch extra for filtering
            scan_index_forward=False,
        )

        # Deserialize and filter
        jobs = [dynamo_deserialize(item) for item in items]
        filtered_jobs = filter_jobs(
            jobs,
            f"USER#{user_sub}",
            min_rating=min_rating,
            status_filter=status_filter,
            sort_by=sort_by,
        )

        # Paginate
        paginated_jobs = filtered_jobs[offset : offset + page_size]

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
