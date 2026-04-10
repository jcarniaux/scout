"""
Dice job crawler using requests + BeautifulSoup.
Dice is not supported by JobSpy, so we do custom scraping.
Triggered by EventBridge on a schedule (daily).
Best-effort: fails gracefully if Dice changes their frontend.
"""
import json
import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

import boto3
import requests
from bs4 import BeautifulSoup

from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import normalize_title, normalize_company, normalize_location, meets_salary_requirement

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")

DICE_BASE_URL = "https://www.dice.com/jobs"
TIMEOUT = 10
MAX_RETRIES = 3


def parse_salary_from_text(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse salary range from job posting text.

    Args:
        text: Job description or salary text

    Returns:
        Tuple of (min_salary, max_salary)
    """
    if not text:
        return None, None

    try:
        # Look for patterns like $180,000 or $180000 or 180K or 180k
        pattern = r"\$?([\d,]+\.?\d*)[kK]?"
        matches = re.findall(pattern, text)

        if not matches:
            return None, None

        salaries = []
        for match in matches:
            try:
                # Remove commas and convert
                clean = match.replace(",", "")
                sal = int(float(clean))
                # If it's a small number (like 3), assume it's in thousands
                if sal < 100:
                    sal = sal * 1000
                salaries.append(sal)
            except ValueError:
                continue

        if not salaries:
            return None, None

        # Return min and max from found salaries
        return min(salaries), max(salaries) if len(salaries) > 1 else salaries[0]
    except Exception as e:
        logger.debug(f"Error parsing salary: {e}")
        return None, None


def scrape_dice_jobs(role: str, location: str, distance: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Scrape Dice.com for jobs.

    Args:
        role: Job role/search term
        location: Location
        distance: Distance radius (Dice may not support this)

    Returns:
        List of job dicts
    """
    jobs = []

    try:
        # Build URL with query parameters
        params = {
            "q": role,
            "location": location,
            "filters.postedDate": "ONE",  # Posted in last day
            "countryCode": "US",
        }

        if distance:
            params["radius"] = distance

        url = f"{DICE_BASE_URL}?{urlencode(params)}"
        logger.info(f"Scraping Dice URL: {url}")

        # Fetch page with retries
        for attempt in range(MAX_RETRIES):
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(url, headers=headers, timeout=TIMEOUT)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise

        # Try to parse JSON from __NEXT_DATA__ script tag
        soup = BeautifulSoup(response.text, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})

        if not script_tag:
            logger.warning("Could not find __NEXT_DATA__ script tag on Dice page")
            return jobs

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError:
            logger.warning("Failed to parse __NEXT_DATA__ JSON")
            return jobs

        # Navigate the JSON structure to find jobs
        # Dice structure varies, so this is defensive
        try:
            # Common paths in Next.js apps
            props = data.get("props", {}).get("pageProps", {})
            job_listings = props.get("job_listings", [])

            if not job_listings and "initialState" in props:
                initial_state = props.get("initialState", {})
                job_listings = initial_state.get("jobs", {}).get("jobs", [])

            for job in job_listings:
                try:
                    title = job.get("title", "").strip()
                    company = job.get("companyName", "").strip()
                    location_str = job.get("location", "").strip()
                    job_url = job.get("jobUrl", job.get("url", "")).strip()
                    description = job.get("description", job.get("summary", "")).strip()
                    posted_date = job.get("postedDate", job.get("datePosted", "")).strip()

                    if not title or not job_url:
                        continue

                    # Extract salary if present
                    salary_min, salary_max = None, None
                    if "salary" in job:
                        salary_str = str(job.get("salary", ""))
                        salary_min, salary_max = parse_salary_from_text(salary_str)
                    elif "salaryRange" in job:
                        salary_range = job.get("salaryRange", {})
                        if isinstance(salary_range, dict):
                            salary_min = salary_range.get("min")
                            salary_max = salary_range.get("max")

                    # Also try parsing salary from description
                    if not salary_min and description:
                        salary_min, salary_max = parse_salary_from_text(description)

                    # Check salary requirement
                    if not meets_salary_requirement(salary_min, SALARY_MINIMUM):
                        logger.debug(f"Skipping {title} - salary too low: {salary_min}")
                        continue

                    job_dict = {
                        "source": "dice",
                        "title": normalize_title(title),
                        "company": normalize_company(company),
                        "location": normalize_location(location_str),
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "job_url": job_url,
                        "date_posted": posted_date,
                        "description": description[:2000],
                        "job_type": job.get("jobType", "").strip(),
                        "crawled_at": datetime.utcnow().isoformat(),
                    }

                    jobs.append(job_dict)

                except Exception as e:
                    logger.debug(f"Error processing individual Dice job: {e}")
                    continue

        except (KeyError, TypeError) as e:
            logger.warning(f"Error navigating Dice JSON structure: {e}")
            return jobs

    except Exception as e:
        logger.error(f"Error scraping Dice for {role} in {location}: {e}", exc_info=True)

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Dice for jobs and send to SQS queue for enrichment.

    Args:
        event: EventBridge event
        context: Lambda context

    Returns:
        Status dict
    """
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set")
        return {"statusCode": 500, "error": "Missing SQS_QUEUE_URL"}

    total_sent = 0
    total_errors = 0

    for role in ROLE_QUERIES:
        for location_config in LOCATIONS:
            location = location_config.get("location")
            distance = location_config.get("distance")
            # Dice doesn't support remote filtering, so skip remote-only queries
            is_remote = location_config.get("remote", False)
            if is_remote:
                continue

            try:
                logger.info(f"Crawling Dice: role={role}, location={location}")

                jobs = scrape_dice_jobs(role, location, distance)
                logger.info(f"Found {len(jobs)} jobs for {role} in {location}")

                # Send each job to SQS
                for job_dict in jobs:
                    try:
                        sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(job_dict, default=str))
                        total_sent += 1
                    except Exception as e:
                        logger.error(f"Error sending job to SQS: {e}")
                        total_errors += 1
                        continue

            except Exception as e:
                logger.error(f"Error crawling Dice for {role} in {location}: {e}", exc_info=True)
                total_errors += 1
                continue

    logger.info(f"Dice crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "dice",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
