"""
Dice job crawler using Dice's public search API.
Triggered by Step Functions as part of the daily crawl pipeline.

Previous approach scraped HTML for __NEXT_DATA__, which broke when Dice
moved to full client-side rendering. This version uses their public
/jobs/q-{query}-jobs endpoint and the underlying search API at
https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search
which returns structured JSON without needing JS rendering.

Best-effort: fails gracefully if Dice changes their API.
"""
import json
import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import boto3
import requests

from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import (
    normalize_title,
    normalize_company,
    normalize_location,
    meets_salary_requirement,
    get_requests_proxy_dict,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")

# Dice's public search API
DICE_API_URL = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
TIMEOUT = 45  # Oxylabs proxy adds latency (TLS interception + anti-bot)
MAX_RETRIES = 3

# User-Agent rotation to reduce blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def parse_salary_from_text(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse salary range from job posting text.

    Handles formats like:
        $180,000 - $220,000
        $180K - $220K
        180000 - 220000

    Returns:
        Tuple of (min_salary, max_salary)
    """
    if not text:
        return None, None

    try:
        # Match dollar amounts with optional K suffix
        pattern = r"\$?([\d,]+(?:\.\d+)?)\s*[kK]?"
        matches = re.findall(pattern, text)

        if not matches:
            return None, None

        salaries = []
        for match in matches:
            try:
                clean = match.replace(",", "")
                sal = int(float(clean))
                # Numbers under 1000 are likely in thousands (e.g., "180K")
                if sal < 1000:
                    sal = sal * 1000
                # Filter out unreasonable values (e.g., years, zip codes)
                if 30000 <= sal <= 1000000:
                    salaries.append(sal)
            except ValueError:
                continue

        if not salaries:
            return None, None

        return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)
    except Exception as e:
        logger.debug(f"Error parsing salary: {e}")
        return None, None


def _get_session() -> requests.Session:
    """
    Create a requests session with proxy from Secrets Manager.

    Uses get_requests_proxy_dict() which handles Oxylabs Web Scraper
    API proxy endpoint (HTTPS proxy + SSL verification skip).
    """
    import random

    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })

    proxy_dict, skip_ssl = get_requests_proxy_dict()

    if proxy_dict:
        session.proxies = proxy_dict
        logger.info(f"Dice session using proxy (skip_ssl={skip_ssl})")

    if skip_ssl:
        # Oxylabs proxy endpoint does TLS termination —
        # the client must skip cert verification on the
        # proxy connection. Suppress the urllib3 warning.
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return session


def scrape_dice_jobs(
    role: str,
    location: str,
    distance: Optional[int] = None,
    is_remote: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search Dice for jobs using their public search API.

    Args:
        role: Job role/search term
        location: Location string
        distance: Distance radius in miles
        is_remote: Filter for remote jobs

    Returns:
        List of job dicts ready for SQS
    """
    jobs = []

    try:
        params = {
            "q": role,
            "countryCode2": "US",
            "radius": distance or 25,
            "radiusUnit": "mi",
            "page": 1,
            "pageSize": 50,
            "fields": "id|jobId|title|summary|description|postedDate|modifiedDate|company|location|salary|jobType|detailsPageUrl",
            "culture": "en",
            "recommendationId": "",
            "interactionId": "0",
            "fj": "true",
            "includeRemote": "true" if is_remote else "false",
        }

        if is_remote:
            params["filters.isRemote"] = "true"

        if not is_remote:
            params["location"] = location

        logger.info(f"Searching Dice API: role={role}, location={location}, remote={is_remote}")

        session = _get_session()

        for attempt in range(MAX_RETRIES):
            try:
                response = session.get(DICE_API_URL, params=params, timeout=TIMEOUT)

                if response.status_code == 429:
                    logger.warning(f"Dice rate limited (429), attempt {attempt + 1}/{MAX_RETRIES}")
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue

                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Dice API attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise

        data = response.json()
        job_listings = data.get("data", [])

        if not job_listings:
            logger.info(f"Dice API returned 0 jobs for {role}")
            return jobs

        logger.info(f"Dice API returned {len(job_listings)} jobs for {role}")

        for job in job_listings:
            try:
                title = (job.get("title") or "").strip()
                company_name = ""
                company_obj = job.get("company", {})
                if isinstance(company_obj, dict):
                    company_name = (company_obj.get("name") or "").strip()
                elif isinstance(company_obj, str):
                    company_name = company_obj.strip()

                location_str = (job.get("location") or "").strip()
                job_url = (job.get("detailsPageUrl") or "").strip()
                if job_url and not job_url.startswith("http"):
                    job_url = f"https://www.dice.com{job_url}"

                description = (job.get("description") or job.get("summary") or "").strip()
                posted_date = (job.get("postedDate") or job.get("modifiedDate") or "").strip()

                if not title or not job_url:
                    continue

                # Parse salary
                salary_min, salary_max = None, None
                salary_str = job.get("salary", "")
                if salary_str:
                    salary_min, salary_max = parse_salary_from_text(str(salary_str))

                # Fallback: try extracting from description
                if salary_min is None and description:
                    salary_min, salary_max = parse_salary_from_text(description[:500])

                if not meets_salary_requirement(salary_min, SALARY_MINIMUM):
                    logger.debug(f"Skipping {title} - salary too low: {salary_min}")
                    continue

                job_dict = {
                    "source": "dice",
                    "title": normalize_title(title),
                    "company": normalize_company(company_name),
                    "location": normalize_location(location_str),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "job_url": job_url,
                    "date_posted": posted_date,
                    "description": description[:2000],
                    "job_type": (job.get("jobType") or "").strip(),
                    "crawled_at": datetime.utcnow().isoformat(),
                }

                jobs.append(job_dict)

            except Exception as e:
                logger.debug(f"Error processing individual Dice job: {e}")
                continue

    except Exception as e:
        logger.error(f"Error searching Dice for {role} in {location}: {e}", exc_info=True)

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Dice for jobs and send to SQS queue for enrichment.
    """
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set")
        return {"statusCode": 500, "error": "Missing SQS_QUEUE_URL"}

    total_sent = 0
    total_errors = 0
    seen_urls: Set[str] = set()

    for role in ROLE_QUERIES:
        for location_config in LOCATIONS:
            location = location_config.get("location")
            distance = location_config.get("distance")
            is_remote = location_config.get("remote", False)

            try:
                logger.info(f"Crawling Dice: role={role}, location={location}, remote={is_remote}")

                jobs = scrape_dice_jobs(
                    role=role,
                    location=location,
                    distance=distance,
                    is_remote=is_remote,
                )
                logger.info(f"Found {len(jobs)} jobs for {role} in {location}")

                for job_dict in jobs:
                    try:
                        job_url = job_dict.get("job_url", "")
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        sqs_client.send_message(
                            QueueUrl=queue_url,
                            MessageBody=json.dumps(job_dict, default=str),
                        )
                        total_sent += 1
                    except Exception as e:
                        logger.error(f"Error sending job to SQS: {e}")
                        total_errors += 1
                        continue

            except Exception as e:
                logger.error(
                    f"Error crawling Dice for {role} in {location}: {e}", exc_info=True
                )
                total_errors += 1
                continue

    logger.info(f"Dice crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "dice",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
