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

# Safety cap: maximum items to fetch from DynamoDB per request.
# Prevents unbounded reads if the dataset grows unexpectedly.
MAX_ITEMS_CAP = 2000

# DynamoDB page size per query call — controls memory per iteration.
DDB_PAGE_SIZE = 200


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

    Expects optional keys "match_score" and "match_reasoning" (integers/strings
    pre-attached by the caller) which are forwarded as matchScore / matchReasoning.
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
        "contractType":   clean(item.get("contract_type")),
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
        # AI match score (None when no resume has been uploaded yet)
        "matchScore":     item.get("match_score"),
        "matchReasoning": clean(item.get("match_reasoning")),
    }


def _load_user_scores(user_id: str, job_hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch AI match scores for a page of jobs in a single DynamoDB round-trip.

    Args:
        user_id:    "USER#{sub}"
        job_hashes: List of raw job hash strings (without the "JOB#" prefix)

    Returns:
        Dict mapping job_hash → {"score": int, "reasoning": str}
    """
    job_scores_table = os.environ.get("JOB_SCORES_TABLE", "")
    if not job_scores_table or not job_hashes:
        return {}

    try:
        keys = [{"pk": user_id, "sk": f"JOB#{h}"} for h in job_hashes]
        items = dynamodb.batch_get_items(job_scores_table, keys)
        result: Dict[str, Dict[str, Any]] = {}
        for item in items:
            sk = item.get("sk", "")  # "JOB#{hash}"
            h = sk[len("JOB#"):] if sk.startswith("JOB#") else sk
            result[h] = {
                "score": int(item["score"]) if item.get("score") is not None else None,
                "reasoning": item.get("reasoning"),
            }
        return result
    except Exception as exc:
        logger.warning(f"Non-blocking: failed to load job scores for {user_id}: {exc}")
        return {}


def _load_user_statuses(user_id: str) -> Dict[str, str]:
    """
    Load all application statuses for a user in a single query.

    Returns:
        Dict mapping job_hash → status string
    """
    user_status_table = os.environ.get("USER_STATUS_TABLE")
    if not user_status_table:
        return {}

    statuses: Dict[str, str] = {}
    try:
        last_key = None
        while True:
            items, last_key = dynamodb.query(
                user_status_table,
                "pk = :pk",
                {":pk": user_id},
                exclusive_start_key=last_key,
            )
            for item in items:
                job_id = item.get("sk", "").replace("JOB#", "")
                statuses[job_id] = item.get("status", "NOT_APPLIED")
            if not last_key:
                break
    except Exception as e:
        logger.warning(f"Error fetching user statuses: {e}")

    return statuses


def _attach_statuses_and_filter(
    jobs: List[Dict[str, Any]],
    user_statuses: Dict[str, str],
    status_filter: Optional[str] = None,
    sources: Optional[List[str]] = None,
    contract_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Attach user statuses to jobs and apply source/status/contract-type filters.

    Args:
        jobs: Deserialized job dicts
        user_statuses: Pre-loaded status map (job_hash → status)
        status_filter: Optional status to filter by
        sources: Optional list of source platforms to include
        contract_types: Optional list of contract types to include
                        (permanent, contract, freelance)

    Returns:
        Filtered job list with user_status attached
    """
    filtered = []
    for job in jobs:
        # Filter by source platform
        if sources and job.get("source", "").lower() not in sources:
            continue

        # Filter by contract type
        if contract_types:
            ct = (job.get("contract_type") or "").lower()
            if ct not in contract_types:
                continue

        # Attach user status
        job_hash = job.get("job_hash")
        if not job_hash:
            pk = job.get("pk", "")
            job_hash = pk[len("JOB#"):] if pk.startswith("JOB#") else pk
        job["user_status"] = user_statuses.get(job_hash) or "NOT_APPLIED"

        # Filter by status
        if status_filter and job["user_status"] != status_filter:
            continue

        filtered.append(job)

    return filtered


def _sort_jobs(jobs: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
    """Sort jobs by the specified field. Mutates and returns the list."""
    if sort_by == "salary":
        jobs.sort(key=lambda x: x.get("salary_min", 0) or 0, reverse=True)
    elif sort_by == "rating":
        jobs.sort(key=lambda x: x.get("rating", 0) or 0, reverse=True)
    elif sort_by == "match":
        # Jobs with no score (None) sink to the bottom
        jobs.sort(key=lambda x: x.get("match_score") if x.get("match_score") is not None else -1, reverse=True)
    else:
        # Default: sort by date (postedDate → created_at fallback)
        jobs.sort(key=lambda x: x.get("postedDate") or x.get("created_at", ""), reverse=True)
    return jobs


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

        # Get user's application status for this job
        user_id = f"USER#{user_sub}"
        user_status_key = {"pk": user_id, "sk": f"JOB#{job_id}"}
        status_item = dynamodb.get_item(user_status_table, user_status_key)
        job["user_status"] = status_item.get("status", "NOT_APPLIED") if status_item else "NOT_APPLIED"

        # Attach AI match score (best-effort — None if no resume or score yet)
        scores = _load_user_scores(user_id, [job_id])
        if job_id in scores:
            job["match_score"] = scores[job_id]["score"]
            job["match_reasoning"] = scores[job_id]["reasoning"]

        return success_response(serialize_job(job))

    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}", exc_info=True)
        return error_response("Error fetching job", 500)


def list_jobs(
    event: Dict[str, Any], context: Any
) -> Dict[str, Any]:
    """
    Handler for GET /jobs with filtering and pagination.

    Uses windowed DynamoDB fetching: queries in controlled pages
    (DDB_PAGE_SIZE items at a time) instead of loading the entire
    dataset into memory. Applies client-side filters progressively
    and stops once we have enough results for the requested page.

    For accurate total counts (needed by the pagination UI), we
    continue fetching beyond the current page. A safety cap
    (MAX_ITEMS_CAP) prevents unbounded reads.
    """
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
        status_filter = query_params.get("status")
        sort_by = query_params.get("sort", "date")
        page = max(1, int(query_params.get("page", "1")))
        page_size = min(50, max(1, int(query_params.get("pageSize", "20"))))
        raw_sources = query_params.get("sources", "")
        sources = [s.strip().lower() for s in raw_sources.split(",") if s.strip()] if raw_sources else None
        raw_contract_types = query_params.get("contractTypes", "")
        contract_types = (
            [c.strip().lower() for c in raw_contract_types.split(",") if c.strip()]
            if raw_contract_types else None
        )

        # Calculate how many filtered items we need
        offset = (page - 1) * page_size
        items_needed = offset + page_size + 1  # +1 to detect hasMore

        start_date = get_date_range_start(date_range)

        # Pre-fetch user statuses in a single query (avoids N+1)
        user_id = f"USER#{user_sub}"
        user_statuses = _load_user_statuses(user_id)

        # ── Windowed DynamoDB fetching ──
        # When no re-sorting is needed (default date sort uses the GSI's
        # native order), we can stop fetching as soon as we have enough
        # filtered results. For salary/rating/match sorts, we need all items.
        needs_full_fetch = sort_by in ("salary", "rating", "match") or status_filter is not None or contract_types is not None
        filtered_jobs: List[Dict[str, Any]] = []
        total_ddb_items = 0
        last_key = None

        while True:
            items, last_key = dynamodb.query(
                jobs_table,
                "gsi1pk = :pk AND postedDate >= :start",
                {":pk": "JOB", ":start": start_date},
                index_name="DateIndex",
                scan_index_forward=False,
                limit=DDB_PAGE_SIZE,
                exclusive_start_key=last_key,
            )

            if items:
                deserialized = [dynamo_deserialize(item) for item in items]
                total_ddb_items += len(deserialized)

                batch_filtered = _attach_statuses_and_filter(
                    deserialized, user_statuses,
                    status_filter=status_filter, sources=sources,
                    contract_types=contract_types,
                )
                filtered_jobs.extend(batch_filtered)

            # Stop conditions
            if not last_key:
                break
            if total_ddb_items >= MAX_ITEMS_CAP:
                logger.warning(
                    f"Hit MAX_ITEMS_CAP ({MAX_ITEMS_CAP}) — results may be truncated"
                )
                break
            # Early exit: if we don't need re-sorting and have enough results
            if not needs_full_fetch and len(filtered_jobs) >= items_needed:
                # We have enough for this page. Fetch one more DDB page to
                # get a better total estimate, then stop.
                if last_key:
                    extra_items, extra_key = dynamodb.query(
                        jobs_table,
                        "gsi1pk = :pk AND postedDate >= :start",
                        {":pk": "JOB", ":start": start_date},
                        index_name="DateIndex",
                        scan_index_forward=False,
                        limit=DDB_PAGE_SIZE,
                        exclusive_start_key=last_key,
                    )
                    if extra_items:
                        extra_deserialized = [dynamo_deserialize(i) for i in extra_items]
                        extra_filtered = _attach_statuses_and_filter(
                            extra_deserialized, user_statuses,
                            status_filter=status_filter, sources=sources,
                            contract_types=contract_types,
                        )
                        filtered_jobs.extend(extra_filtered)
                break

        # Sort (only needed for non-date sorts; date sort comes from GSI order)
        if sort_by in ("salary", "rating", "match"):
            # For match sort, pre-fetch scores for ALL filtered jobs so we can sort
            if sort_by == "match":
                all_hashes = [
                    (j.get("job_hash") or (j.get("pk", "")[len("JOB#"):]
                     if j.get("pk", "").startswith("JOB#") else ""))
                    for j in filtered_jobs
                ]
                all_scores = _load_user_scores(user_id, [h for h in all_hashes if h])
                for job, h in zip(filtered_jobs, all_hashes):
                    if h in all_scores:
                        job["match_score"] = all_scores[h]["score"]
                        job["match_reasoning"] = all_scores[h]["reasoning"]
            _sort_jobs(filtered_jobs, sort_by)

        # Paginate
        total = len(filtered_jobs)
        page_slice = filtered_jobs[offset : offset + page_size]

        # Attach match scores for this page (single batch call, unless already loaded)
        if sort_by != "match":
            page_hashes = [
                job.get("job_hash") or (job.get("pk", "")[len("JOB#"):]
                if job.get("pk", "").startswith("JOB#") else "")
                for job in page_slice
            ]
            page_scores = _load_user_scores(user_id, [h for h in page_hashes if h])
            for job, h in zip(page_slice, page_hashes):
                if h in page_scores:
                    job["match_score"] = page_scores[h]["score"]
                    job["match_reasoning"] = page_scores[h]["reasoning"]

        # Serialize to frontend camelCase shape
        paginated_jobs = [serialize_job(j) for j in page_slice]

        return success_response({
            "jobs": paginated_jobs,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "hasMore": total > offset + page_size,
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
