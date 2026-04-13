"""
SQS-triggered enrichment Lambda for Scout job postings.
Deduplicates jobs, enriches with benefits info and ratings, and stores in DynamoDB.

AI Scoring:
  After each new job is stored, Bedrock Claude Haiku scores it against every user
  that has a ready resume. Scores are stored in the scout-job-scores table.
  Scoring is always best-effort — any failure is logged and skipped so job
  storage is never blocked.
"""
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import boto3
import requests

from shared.db import DynamoDBHelper
from shared.metrics import emit_metric
from shared.models import dynamo_serialize
from shared.crawler_utils import meets_location_requirement

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
requests_session = requests.Session()
requests_session.timeout = 5

# ── Bedrock client (container-level, reused across warm invocations) ──────────
_bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# ── Users-with-resumes cache (5-min TTL, per Lambda container) ────────────────
_users_cache: List[Dict[str, Any]] = []
_users_cache_time: float = 0.0
_USERS_CACHE_TTL = 300  # seconds


def compute_job_hash(title: str, company: str, location: str, job_url: str = "") -> str:
    """
    Compute a hash for job deduplication.
    Uses job_url as primary key when company is unknown (common with LinkedIn scrapes).

    Args:
        title: Job title
        company: Company name (may be "Unknown")
        location: Location
        job_url: Job URL (used as tiebreaker when company is missing)

    Returns:
        SHA256 hash hex
    """
    if job_url and (not company or company == "Unknown"):
        # URL is the most reliable dedup key when company data is absent
        key = job_url.strip()
    else:
        key = f"{title.lower().strip()}|{company.lower().strip()}|{location.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


def extract_benefits(description: str) -> List[str]:
    """
    Extract benefits from job description using keyword matching.

    Args:
        description: Job description text

    Returns:
        List of benefits found
    """
    benefits = set()
    desc_lower = description.lower()

    # PTO patterns
    if re.search(r"(\d+\s*(days?|weeks?)\s*(paid\s+)?pto|unlimited\s+pto|pto|paid\s+time\s+off)", desc_lower):
        benefits.add("PTO")

    # Sick days
    if re.search(r"(\d+\s*sick\s*days?|sick\s*leave)", desc_lower):
        benefits.add("Sick Days")

    # 401k
    if re.search(r"(401\(k\)\s*match|\d+\%\s*match|401k|retirement)", desc_lower):
        benefits.add("401(k)")

    # Health insurance
    if re.search(r"(medical|health\s+insurance|health\s+coverage)", desc_lower):
        benefits.add("Medical")

    if re.search(r"(dental|dental\s+insurance)", desc_lower):
        benefits.add("Dental")

    if re.search(r"(vision|vision\s+insurance)", desc_lower):
        benefits.add("Vision")

    # Flexible spending
    if re.search(r"(hsa|health\s+savings\s+account)", desc_lower):
        benefits.add("HSA")

    if re.search(r"(fsa|flexible\s+spending)", desc_lower):
        benefits.add("FSA")

    # Education benefits
    if re.search(r"(tuition|education|learning|professional\s+development)", desc_lower):
        benefits.add("Tuition Reimbursement")

    # Remote/flexible
    if re.search(r"(remote|work\s+from\s+home|flexible\s+work|wfh)", desc_lower):
        benefits.add("Remote Work")

    # Stock options
    if re.search(r"(stock\s+options?|equity)", desc_lower):
        benefits.add("Stock Options")

    return sorted(list(benefits))


def fetch_glassdoor_rating(company: str, cache_table: str) -> Optional[float]:
    """
    Fetch Glassdoor rating for a company.
    Uses cache table to avoid repeated lookups.

    Args:
        company: Company name
        cache_table: Cache table name

    Returns:
        Rating as float or None
    """
    try:
        company_key = company.lower().strip()

        # Check cache first — table primary key is "pk"
        cached = dynamodb.get_item(cache_table, {"pk": company_key})

        if cached:
            rating = cached.get("rating")
            if rating is not None:
                logger.info(f"Cache hit for {company}: {rating}")
                return float(rating)

            # Check if we recently failed to find this company
            last_checked = cached.get("last_checked")
            if last_checked:
                last_checked_dt = datetime.fromisoformat(last_checked)
                if datetime.utcnow() - last_checked_dt < timedelta(days=7):
                    logger.info(f"Company {company} recently checked, skipping")
                    return None

        # Try to scrape Glassdoor (best effort)
        logger.info(f"Fetching Glassdoor rating for {company}")
        try:
            # This is a simplified approach; real implementation would need more robust parsing
            search_url = f"https://www.glassdoor.com/Search/results.htm?keyword={company}&sc.location=United+States"
            response = requests_session.get(search_url, headers={"User-Agent": "Scout Bot"}, timeout=5)

            # Try to extract rating from page
            # This is fragile and depends on Glassdoor's HTML structure
            rating_match = re.search(r'"companyRating":\s*(\d+\.?\d*)', response.text)
            if rating_match:
                rating = float(rating_match.group(1))

                # Cache the result with 7-day TTL
                ttl = int((datetime.utcnow() + timedelta(days=7)).timestamp())
                cache_item = {
                    "pk": company_key,
                    "rating": rating,
                    "last_checked": datetime.utcnow().isoformat(),
                    "ttl": ttl,
                }
                dynamodb.put_item(cache_table, dynamo_serialize(cache_item))
                logger.info(f"Cached rating for {company}: {rating}")
                return rating
        except Exception as e:
            logger.debug(f"Error fetching Glassdoor rating: {e}")

        # Cache the failed attempt
        ttl = int((datetime.utcnow() + timedelta(days=7)).timestamp())
        cache_item = {
            "pk": company_key,
            "last_checked": datetime.utcnow().isoformat(),
            "ttl": ttl,
        }
        dynamodb.put_item(cache_table, dynamo_serialize(cache_item))

    except Exception as e:
        logger.error(f"Error in fetch_glassdoor_rating: {e}")

    return None


def _get_users_with_resumes() -> List[Dict[str, Any]]:
    """
    Return all users that have a ready resume, using a 5-minute in-process cache.

    Scans the USERS_TABLE and filters for items where resume_status == "ready"
    and resume_text is present. The scan result is cached at the container level
    so a busy Lambda instance (many SQS messages) only hits DynamoDB once per
    5-minute window instead of on every message.

    Returns:
        List of user items with at least {"pk": "USER#<sub>", "resume_text": "..."}
    """
    global _users_cache, _users_cache_time

    users_table = os.environ.get("USERS_TABLE", "")
    if not users_table:
        return []

    now = time.monotonic()
    if _users_cache and (now - _users_cache_time) < _USERS_CACHE_TTL:
        return _users_cache

    try:
        items, last_key = dynamodb.scan(
            users_table,
            filter_expression="resume_status = :s AND attribute_exists(resume_text)",
            expression_attribute_values={":s": "ready"},
            projection_expression="pk, resume_text",
        )
        # Handle pagination (unlikely to need it for a handful of users)
        while last_key:
            page, last_key = dynamodb.scan(
                users_table,
                filter_expression="resume_status = :s AND attribute_exists(resume_text)",
                expression_attribute_values={":s": "ready"},
                projection_expression="pk, resume_text",
                exclusive_start_key=last_key,
            )
            items.extend(page)

        _users_cache = items
        _users_cache_time = now
        logger.info(f"Loaded {len(items)} users with ready resumes (cache refreshed)")
    except Exception as exc:
        logger.error(f"Failed to load users with resumes: {exc}")
        # Return stale cache rather than failing the whole invocation
        return _users_cache

    return _users_cache


def _score_job_for_user(
    job_item: Dict[str, Any],
    user: Dict[str, Any],
) -> Tuple[int, str]:
    """
    Ask Bedrock Claude Haiku to score a job against a user's resume.

    The prompt is deliberately short to minimize token usage and latency with
    Claude Haiku — the cheapest and fastest Bedrock model.

    Args:
        job_item: Enriched job dict (must have title, company, description)
        user:     User item with resume_text

    Returns:
        Tuple of (score 0–100, one-sentence reasoning)

    Raises:
        Exception on any Bedrock or JSON parse failure (caller wraps in try/except)
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    resume_excerpt = (user.get("resume_text") or "")[:2000]
    description_excerpt = (job_item.get("description") or "")[:1500]

    prompt = (
        "Score this job posting against the candidate's resume on a 0-100 scale.\n\n"
        f"Resume:\n{resume_excerpt}\n\n"
        f"Job Title: {job_item.get('title', '')}\n"
        f"Company: {job_item.get('company', '')}\n"
        f"Description:\n{description_excerpt}\n\n"
        'Return ONLY valid JSON: {"score": <integer 0-100>, "reasoning": "<one concise sentence>"}'
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 120,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = _bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    raw = json.loads(response["body"].read())
    text = raw["content"][0]["text"].strip()

    # Strip any markdown code fences Haiku occasionally adds
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()

    result = json.loads(text)
    score = max(0, min(100, int(result["score"])))
    reasoning = str(result.get("reasoning", ""))[:500]
    return score, reasoning


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process SQS messages containing raw job postings.
    Enriches and deduplicates before storing in DynamoDB.

    Args:
        event: SQS event
        context: Lambda context

    Returns:
        Status dict
    """
    jobs_table = os.environ.get("JOBS_TABLE")
    glassdoor_cache_table = os.environ.get("GLASSDOOR_CACHE_TABLE")
    job_scores_table = os.environ.get("JOB_SCORES_TABLE", "")

    if not jobs_table or not glassdoor_cache_table:
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "error": "Missing environment variables"}

    total_processed = 0
    total_stored = 0
    total_duplicates = 0
    total_filtered = 0
    total_scored = 0
    batch_item_failures: List[Dict[str, str]] = []

    # Load users-with-resumes once per invocation (cached at container level)
    users_with_resumes = _get_users_with_resumes() if job_scores_table else []

    # Get TTL (60 days from now)
    ttl = int((datetime.utcnow() + timedelta(days=60)).timestamp())

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        try:
            # Parse SQS message
            body = json.loads(record["body"])

            # Normalize job data
            title = body.get("title", "").strip()
            company = body.get("company", "").strip()
            location = body.get("location", "").strip()
            source = body.get("source", "unknown").strip()

            # Only require title + url — company is often missing from LinkedIn scrapes
            job_url = body.get("job_url", "").strip()
            if not title or not job_url:
                logger.warning(f"Skipping job with missing title or url: {body}")
                total_filtered += 1
                continue

            # Location filter — only store Atlanta/GA or remote jobs
            if not meets_location_requirement(location):
                logger.info(f"Skipping out-of-area job: '{title}' at '{location}'")
                total_filtered += 1
                continue

            # Fall back to "Unknown" so the job is still stored and searchable
            if not company:
                company = "Unknown"

            total_processed += 1

            # Compute hash for deduplication
            job_hash = compute_job_hash(title, company, location, job_url)

            # Build job item for DynamoDB.
            # Key names must match the table schema exactly (case-sensitive):
            #   pk / sk       — primary key (lowercase, as defined in Terraform)
            #   gsi1pk        — DateIndex / RatingIndex partition key (value = "JOB")
            #   postedDate    — DateIndex range key (ISO string for date-range queries)

            # JobSpy returns Python's NaN/None for missing dates, which json.dumps
            # renders as the string "nan" or "None". Normalize these to None so
            # the DateIndex range key is omitted (or gets today's date as fallback).
            raw_date = body.get("date_posted", "")
            if not raw_date or str(raw_date).lower() in ("nan", "none", "null", ""):
                raw_date = None
            posted_date = raw_date or datetime.utcnow().date().isoformat()
            job_item = {
                "pk": f"JOB#{job_hash}",
                "sk": f"SOURCE#{source}#{hashlib.md5(body.get('job_url', '').encode()).hexdigest()}",
                "gsi1pk": "JOB",           # Required for DateIndex and RatingIndex queries
                "postedDate": posted_date, # DateIndex range key
                "job_hash": job_hash,
                "source": source,
                "title": title,
                "company": company,
                "location": location,
                "salary_min": body.get("salary_min"),
                "salary_max": body.get("salary_max"),
                "job_url": body.get("job_url", "").strip(),
                "date_posted": posted_date,
                "description": (body.get("description") or "")[:2000] if str(body.get("description", "")).lower() not in ("none", "nan", "null") else "",
                "job_type": body.get("job_type", "").strip() if str(body.get("job_type", "")).lower() not in ("none", "nan", "null") else None,
                "created_at": datetime.utcnow().isoformat(),
                "crawled_at": body.get("crawled_at", datetime.utcnow().isoformat()),
                "ttl": ttl,
            }

            # Extract benefits from description
            benefits = extract_benefits(body.get("description", ""))
            if benefits:
                job_item["benefits"] = benefits

            # ── Store the job first, THEN attempt rating lookup ──
            # This ensures the job is persisted even if the Glassdoor HTTP
            # call is slow or fails. Rating is applied as a post-write update.
            try:
                dynamodb.put_item(
                    jobs_table,
                    dynamo_serialize(job_item),
                    condition_expression="attribute_not_exists(pk)",
                )
                total_stored += 1
                logger.info(f"Stored job: {title} at {company}")

                # ── Per-user AI scoring (best-effort, never blocks storage) ──
                if job_scores_table and users_with_resumes:
                    for user in users_with_resumes:
                        user_pk = user.get("pk", "")  # e.g. "USER#<sub>"
                        if not user_pk:
                            continue
                        try:
                            score, reasoning = _score_job_for_user(job_item, user)
                            score_item = {
                                "pk": user_pk,
                                "sk": f"JOB#{job_hash}",
                                "score": score,
                                "reasoning": reasoning,
                                "scored_at": datetime.utcnow().isoformat(),
                                "ttl": ttl,
                            }
                            dynamodb.put_item(job_scores_table, score_item)
                            total_scored += 1
                            logger.info(
                                f"Score {score}/100 for user {user_pk} on job {job_hash[:8]}… "
                                f"({title} @ {company})"
                            )
                        except Exception as score_err:
                            logger.warning(
                                f"Non-blocking: scoring failed for user {user_pk} "
                                f"on job {job_hash[:8]}…: {score_err}"
                            )

            except Exception as e:
                if "ConditionalCheckFailedException" in str(e):
                    total_duplicates += 1
                    # Refresh the crawled_at timestamp so the frontend's
                    # "Last updated" reflects the most recent crawl, not
                    # the original insertion date.
                    try:
                        dynamodb.update_item(
                            jobs_table,
                            {"pk": job_item["pk"], "sk": job_item["sk"]},
                            "SET crawled_at = :ca, created_at = :ca",
                            {":ca": datetime.utcnow().isoformat()},
                        )
                    except Exception as ue:
                        logger.debug(f"Failed to refresh timestamp for {title}: {ue}")
                else:
                    raise

            # Best-effort Glassdoor rating — applied as a separate update so
            # the HTTP call never blocks or prevents the job from being stored.
            try:
                rating = fetch_glassdoor_rating(company, glassdoor_cache_table)
                if rating is not None:
                    dynamodb.update_item(
                        jobs_table,
                        {"pk": job_item["pk"], "sk": job_item["sk"]},
                        "SET rating = :r, glassdoorRating = :r",
                        {":r": rating},
                    )
            except Exception as re_err:
                logger.debug(f"Non-blocking: Glassdoor rating failed for {company}: {re_err}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse SQS message: {record}")
            # Malformed JSON won't succeed on retry — don't report as failure
        except Exception as e:
            logger.error(f"Error processing SQS record {message_id}: {e}", exc_info=True)
            # Report this message for retry via ReportBatchItemFailures
            batch_item_failures.append({"itemIdentifier": message_id})

    logger.info(
        f"Enrichment complete: {total_processed} processed, "
        f"{total_stored} stored, {total_duplicates} duplicates, "
        f"{total_filtered} filtered, {total_scored} scored, "
        f"{len(batch_item_failures)} failures"
    )

    # Emit custom CloudWatch metrics via Embedded Metric Format
    emit_metric("Scout/Enrichment", "JobsProcessed", total_processed)
    emit_metric("Scout/Enrichment", "JobsStored", total_stored)
    emit_metric("Scout/Enrichment", "JobsDuplicate", total_duplicates)
    emit_metric("Scout/Enrichment", "JobsFiltered", total_filtered)
    emit_metric("Scout/Enrichment", "JobsScored", total_scored)
    emit_metric("Scout/Enrichment", "BatchFailures", len(batch_item_failures))

    return {"batchItemFailures": batch_item_failures}
