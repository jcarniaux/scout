"""
SQS-triggered enrichment Lambda for Scout job postings.
Deduplicates jobs, enriches with benefits info and ratings, and stores in DynamoDB.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

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

    if not jobs_table or not glassdoor_cache_table:
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "error": "Missing environment variables"}

    total_processed = 0
    total_stored = 0
    total_duplicates = 0
    total_filtered = 0
    batch_item_failures: List[Dict[str, str]] = []

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
        f"{total_filtered} filtered, {len(batch_item_failures)} failures"
    )

    # Emit custom CloudWatch metrics via Embedded Metric Format
    emit_metric("Scout/Enrichment", "JobsProcessed", total_processed)
    emit_metric("Scout/Enrichment", "JobsStored", total_stored)
    emit_metric("Scout/Enrichment", "JobsDuplicate", total_duplicates)
    emit_metric("Scout/Enrichment", "JobsFiltered", total_filtered)
    emit_metric("Scout/Enrichment", "BatchFailures", len(batch_item_failures))

    return {"batchItemFailures": batch_item_failures}
