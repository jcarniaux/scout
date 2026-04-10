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
from shared.models import dynamo_serialize

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
requests_session = requests.Session()
requests_session.timeout = 5


def compute_job_hash(title: str, company: str, location: str) -> str:
    """
    Compute a hash for job deduplication.

    Args:
        title: Job title
        company: Company name
        location: Location

    Returns:
        SHA256 hash hex
    """
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

        # Check cache first
        cached = dynamodb.get_item(cache_table, {"company_normalized": company_key})

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
                    "company_normalized": company_key,
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
            "company_normalized": company_key,
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
    total_errors = 0

    # Get TTL (60 days from now)
    ttl = int((datetime.utcnow() + timedelta(days=60)).timestamp())

    for record in event.get("Records", []):
        try:
            # Parse SQS message
            body = json.loads(record["body"])

            # Normalize job data
            title = body.get("title", "").strip()
            company = body.get("company", "").strip()
            location = body.get("location", "").strip()
            source = body.get("source", "unknown").strip()

            if not title or not company:
                logger.warning(f"Skipping job with missing title or company: {body}")
                total_errors += 1
                continue

            total_processed += 1

            # Compute hash for deduplication
            job_hash = compute_job_hash(title, company, location)

            # Build job item for DynamoDB
            job_item = {
                "PK": f"JOB#{job_hash}",
                "SK": f"SOURCE#{source}#{hashlib.md5(body.get('job_url', '').encode()).hexdigest()}",
                "job_hash": job_hash,
                "source": source,
                "title": title,
                "company": company,
                "location": location,
                "salary_min": body.get("salary_min"),
                "salary_max": body.get("salary_max"),
                "job_url": body.get("job_url", "").strip(),
                "date_posted": body.get("date_posted", "").strip(),
                "description": body.get("description", "")[:2000],
                "job_type": body.get("job_type", "").strip(),
                "created_at": datetime.utcnow().isoformat(),
                "crawled_at": body.get("crawled_at", datetime.utcnow().isoformat()),
                "ttl": ttl,
            }

            # Extract benefits from description
            benefits = extract_benefits(body.get("description", ""))
            if benefits:
                job_item["benefits"] = benefits

            # Try to fetch Glassdoor rating (best effort)
            rating = fetch_glassdoor_rating(company, glassdoor_cache_table)
            if rating is not None:
                job_item["rating"] = rating

            # Store in DynamoDB with conditional put (skip if job+source already exists)
            try:
                dynamodb.put_item(
                    jobs_table,
                    dynamo_serialize(job_item),
                    condition_expression="attribute_not_exists(PK)",
                )
                total_stored += 1
                logger.info(f"Stored job: {title} at {company}")
            except Exception as e:
                if "ConditionalCheckFailedException" in str(e):
                    total_duplicates += 1
                    logger.debug(f"Duplicate job skipped: {title}")
                else:
                    raise

        except json.JSONDecodeError:
            logger.error(f"Failed to parse SQS message: {record}")
            total_errors += 1
        except Exception as e:
            logger.error(f"Error processing SQS record: {e}", exc_info=True)
            total_errors += 1

    logger.info(
        f"Enrichment complete: {total_processed} processed, "
        f"{total_stored} stored, {total_duplicates} duplicates, {total_errors} errors"
    )

    return {
        "statusCode": 200,
        "processed": total_processed,
        "stored": total_stored,
        "duplicates": total_duplicates,
        "errors": total_errors,
    }
