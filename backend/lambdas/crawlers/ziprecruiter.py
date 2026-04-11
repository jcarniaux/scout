"""
ZipRecruiter job crawler using Oxylabs Web Scraper API (Realtime).

Fetches rendered ZipRecruiter search result pages via Oxylabs, then
parses job cards from the HTML using BeautifulSoup.

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

ZIPRECRUITER_BASE = "https://www.ziprecruiter.com/jobs-search"


def _build_search_url(
    role: str, location: str, distance: Optional[int], is_remote: bool
) -> str:
    """
    Build a ZipRecruiter search URL.

    ZipRecruiter URL params:
      search   = search query
      location = location
      radius   = distance in miles
      days     = max days since posting (1 = last 24h)
      remote   = remote filter (1 = remote only)
    """
    params = {
        "search": role,
        "location": location,
        "days": "1",
    }

    if is_remote:
        params["remote"] = "1"
    elif distance:
        params["radius"] = str(distance)

    return f"{ZIPRECRUITER_BASE}?{urlencode(params, quote_via=quote_plus)}"


def _parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse salary from text like "$180,000 - $220,000 a year"."""
    if not text:
        return None, None

    matches = re.findall(r"\$?([\d,]+(?:\.\d+)?)", text)
    if not matches:
        return None, None

    salaries = []
    for m in matches:
        try:
            val = int(float(m.replace(",", "")))
            if val < 1000:
                val = val * 2080  # Hourly to annual
            if 30000 <= val <= 1_000_000:
                salaries.append(val)
        except ValueError:
            continue

    if not salaries:
        return None, None

    return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from a ZipRecruiter search results page.

    ZipRecruiter renders job cards in article elements or list items.
    Each card contains a title link, company, location, and salary info.
    """
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Modern ZipRecruiter — article-based cards
    job_cards = soup.select("article.job_result")
    if not job_cards:
        # Strategy 2: Card-based layout
        job_cards = soup.select("[data-testid='job-card']")
    if not job_cards:
        # Strategy 3: List-based layout
        job_cards = soup.select(".jobList > article") or soup.select(
            ".job_results_list > div"
        )
    if not job_cards:
        # Strategy 4: Try finding by title links
        job_cards = soup.select("[data-job-id]")
    if not job_cards:
        # Strategy 5: Broadest — look for containers with job title links
        container = soup.select_one("#job_results_list") or soup.select_one(
            ".job_results"
        )
        if container:
            job_cards = container.find_all(
                ["article", "div", "li"], class_=re.compile(r"job"), recursive=False
            )

    logger.info(f"Found {len(job_cards)} job cards in ZipRecruiter HTML")

    for card in job_cards:
        try:
            # Title
            title_el = (
                card.select_one("h2.job_title a")
                or card.select_one(".job_title a")
                or card.select_one("[data-testid='job-title'] a")
                or card.select_one("a.job_link")
                or card.select_one("h2 a")
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Job URL
            job_url = ""
            link_el = title_el if title_el and title_el.name == "a" else None
            if not link_el:
                link_el = card.select_one("a[href*='/jobs/']") or card.select_one(
                    "a[href*='ziprecruiter.com']"
                )
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.ziprecruiter.com{href}"
                elif href.startswith("http"):
                    job_url = href

            # Company
            company_el = (
                card.select_one("[data-testid='company-name']")
                or card.select_one(".hiring_company .t_org_link")
                or card.select_one("a.t_org_link")
                or card.select_one(".company_name")
            )
            company = company_el.get_text(strip=True) if company_el else ""

            # Location
            location_el = (
                card.select_one("[data-testid='job-location']")
                or card.select_one(".job_location")
                or card.select_one(".location")
            )
            location = location_el.get_text(strip=True) if location_el else ""

            # Salary
            salary_el = (
                card.select_one("[data-testid='salary']")
                or card.select_one(".job_salary")
                or card.select_one(".salary")
            )
            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            salary_min, salary_max = _parse_salary(salary_text)

            # Date posted
            date_el = (
                card.select_one("[data-testid='posted-date']")
                or card.select_one(".posted_time")
                or card.select_one("time")
            )
            date_posted = date_el.get_text(strip=True) if date_el else ""

            # Snippet/description
            desc_el = card.select_one(".job_snippet") or card.select_one(
                "[data-testid='job-snippet']"
            )
            description = desc_el.get_text(strip=True) if desc_el else ""

            if not title or not job_url:
                continue

            jobs.append({
                "source": "ziprecruiter",
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
            logger.debug(f"Error parsing ZipRecruiter job card: {e}")
            continue

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl ZipRecruiter for jobs using Oxylabs and send to SQS.
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
                logger.info(
                    f"Crawling ZipRecruiter: role={role}, location={location}, remote={is_remote}"
                )

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
                    f"Error crawling ZipRecruiter for {role} in {location}: {e}",
                    exc_info=True,
                )
                total_errors += 1

    logger.info(f"ZipRecruiter crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "ziprecruiter",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
