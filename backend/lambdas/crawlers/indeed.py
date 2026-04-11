"""
Indeed job crawler using Oxylabs Web Scraper API (Realtime).

Fetches rendered Indeed search result pages via Oxylabs, then parses
job cards from the HTML using BeautifulSoup. This avoids the TLS
interception issues that occur when routing JobSpy through a proxy.

Triggered by Step Functions as part of the daily crawl pipeline.
"""
import json
import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlencode, quote_plus

import boto3
from bs4 import BeautifulSoup

from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import meets_salary_requirement
from shared.oxylabs_client import OxylabsClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")

INDEED_BASE = "https://www.indeed.com/jobs"


def _build_search_url(role: str, location: str, distance: Optional[int], is_remote: bool) -> str:
    """
    Build an Indeed search URL.

    Indeed URL params:
      q       = search query
      l       = location
      radius  = distance in miles
      fromage = max days since posting (1 = last 24h)
      sort    = date (newest first)
      remotejob = remote filter UUID
    """
    params = {
        "q": role,
        "l": location,
        "fromage": "1",
        "sort": "date",
    }

    if is_remote:
        # Indeed's remote job filter
        params["sc"] = "0kf:attr(DSQF7);"
    elif distance:
        params["radius"] = str(distance)

    return f"{INDEED_BASE}?{urlencode(params, quote_via=quote_plus)}"


def _parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse salary from text like "$180,000 - $220,000 a year".

    Returns (min_salary, max_salary).
    """
    if not text:
        return None, None

    # Match dollar amounts
    matches = re.findall(r"\$?([\d,]+(?:\.\d+)?)", text)
    if not matches:
        return None, None

    salaries = []
    for m in matches:
        try:
            val = int(float(m.replace(",", "")))
            # If it looks like hourly (< 1000), convert to annual
            if val < 1000:
                val = val * 2080  # ~40h/week * 52 weeks
            if 30000 <= val <= 1_000_000:
                salaries.append(val)
        except ValueError:
            continue

    if not salaries:
        return None, None

    return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from an Indeed search results page.

    Indeed renders job cards inside elements with data-jk attribute
    (the job key). Each card contains title, company, location,
    salary (optional), and a link to the full posting.
    """
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    # Indeed job cards: try multiple selectors for resilience
    job_cards = soup.select("[data-jk]")
    if not job_cards:
        job_cards = soup.select(".job_seen_beacon")
    if not job_cards:
        job_cards = soup.select(".jobsearch-ResultsList > li")

    logger.info(f"Found {len(job_cards)} job cards in Indeed HTML")

    for card in job_cards:
        try:
            # Title
            title_el = (
                card.select_one("h2.jobTitle a span")
                or card.select_one("h2.jobTitle span")
                or card.select_one(".jobTitle span")
                or card.select_one("a[data-jk] span")
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Job URL
            link_el = (
                card.select_one("h2.jobTitle a")
                or card.select_one("a[data-jk]")
                or card.select_one("a.jcs-JobTitle")
            )
            job_url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.indeed.com{href}"
                elif href.startswith("http"):
                    job_url = href

            # Company
            company_el = (
                card.select_one("[data-testid='company-name']")
                or card.select_one(".companyName")
                or card.select_one(".company")
            )
            company = company_el.get_text(strip=True) if company_el else ""

            # Location
            location_el = (
                card.select_one("[data-testid='text-location']")
                or card.select_one(".companyLocation")
                or card.select_one(".location")
            )
            location = location_el.get_text(strip=True) if location_el else ""

            # Salary (optional — many Indeed listings omit this)
            salary_el = (
                card.select_one("[data-testid='attribute_snippet_testid']")
                or card.select_one(".salary-snippet-container")
                or card.select_one(".salaryText")
                or card.select_one(".estimated-salary")
            )
            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            salary_min, salary_max = _parse_salary(salary_text)

            # Date posted (relative, e.g., "Just posted", "1 day ago")
            date_el = (
                card.select_one(".date")
                or card.select_one("[data-testid='myJobsStateDate']")
                or card.select_one(".result-footer .date")
            )
            date_posted = date_el.get_text(strip=True) if date_el else ""

            # Description snippet
            desc_el = card.select_one(".job-snippet") or card.select_one(".underShelfFooter")
            description = desc_el.get_text(strip=True) if desc_el else ""

            if not title or not job_url:
                continue

            jobs.append({
                "source": "indeed",
                "title": title,
                "company": company,
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "job_url": job_url,
                "date_posted": date_posted,
                "description": description[:2000],
                "job_type": "",
                "crawled_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.debug(f"Error parsing Indeed job card: {e}")
            continue

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Indeed for jobs using Oxylabs and send to SQS.
    """
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set")
        return {"statusCode": 500, "error": "Missing SQS_QUEUE_URL"}

    try:
        client = OxylabsClient()
    except RuntimeError as e:
        logger.error(f"Failed to init OxylabsClient: {e}")
        return {"statusCode": 500, "error": str(e)}

    total_sent = 0
    total_errors = 0
    seen_urls: Set[str] = set()

    for role in ROLE_QUERIES:
        for location_config in LOCATIONS:
            location = location_config.get("location")
            distance = location_config.get("distance")
            is_remote = location_config.get("remote", False)

            try:
                url = _build_search_url(role, location, distance, is_remote)
                logger.info(f"Crawling Indeed: role={role}, location={location}, remote={is_remote}")

                html = client.fetch_page(url)
                if not html:
                    logger.warning(f"No HTML returned for {role} in {location}")
                    total_errors += 1
                    continue

                jobs = _parse_jobs_from_html(html)
                logger.info(f"Parsed {len(jobs)} jobs for {role} in {location}")

                for job in jobs:
                    try:
                        job_url = job.get("job_url", "")
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        if not meets_salary_requirement(job.get("salary_min"), SALARY_MINIMUM):
                            continue

                        sqs_client.send_message(
                            QueueUrl=queue_url,
                            MessageBody=json.dumps(job, default=str),
                        )
                        total_sent += 1

                    except Exception as e:
                        logger.error(f"Error sending job to SQS: {e}")
                        total_errors += 1

            except Exception as e:
                logger.error(
                    f"Error crawling Indeed for {role} in {location}: {e}", exc_info=True
                )
                total_errors += 1

    logger.info(f"Indeed crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "indeed",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
