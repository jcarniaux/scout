"""
Dice job crawler using Oxylabs Web Scraper API (Realtime).

Fetches rendered Dice search result pages via Oxylabs, then
parses job cards from the HTML using BeautifulSoup.

Previous approach used Dice's public JSON search API directly,
but Dice blocks proxy IPs with HTTP 550 responses. The Oxylabs
Realtime API handles anti-bot and IP rotation on their side.

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

DICE_BASE = "https://www.dice.com/jobs"


def _build_search_url(
    role: str, location: str, distance: Optional[int], is_remote: bool
) -> str:
    """
    Build a Dice job search URL.

    Dice URL params:
      q        = search query
      location = location string
      radius   = distance in miles
      datePosted = date filter (1 = last 24h)
      remoteFilter = remote filter value
    """
    params = {
        "q": role,
        "countryCode": "US",
        "datePosted": "1",
    }

    if is_remote:
        params["remoteFilter"] = "2"  # 2 = remote only on Dice
        params["location"] = "United States"
    else:
        params["location"] = location
        if distance:
            params["radius"] = str(distance)

    return f"{DICE_BASE}?{urlencode(params, quote_via=quote_plus)}"


def _parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse salary from text like "$180,000 - $220,000 Per Year"."""
    if not text:
        return None, None

    matches = re.findall(r"\$?([\d,]+(?:\.\d+)?)", text)
    if not matches:
        return None, None

    salaries = []
    is_hourly = bool(re.search(r"(?i)per\s*hour|/hr|hourly", text))

    for m in matches:
        try:
            val = int(float(m.replace(",", "")))
            if is_hourly and val < 500:
                val = val * 2080  # Hourly to annual (40h/week × 52 weeks)
            elif val < 1000:
                val = val * 1000  # "180K" format
            if 30000 <= val <= 1_000_000:
                salaries.append(val)
        except ValueError:
            continue

    if not salaries:
        return None, None

    return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from a Dice search results page.

    Dice is a Next.js app that renders job cards in a search results list.
    The structure changes with deploys, so we use multiple fallback strategies.
    """
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Dice uses custom web components / shadow DOM elements
    # Look for dhi-search-card or similar custom elements
    job_cards = soup.select("dhi-search-card")
    if not job_cards:
        # Strategy 2: Card-based layout with data attributes
        job_cards = soup.select("[data-cy='search-card']")
    if not job_cards:
        # Strategy 3: Generic card containers
        job_cards = soup.select(".card.search-card")
    if not job_cards:
        # Strategy 4: List items in search results
        results_container = (
            soup.select_one("[data-cy='search-results']")
            or soup.select_one("#searchDisplay")
            or soup.select_one(".search-results-container")
        )
        if results_container:
            job_cards = results_container.find_all(
                ["div", "li", "article"],
                class_=re.compile(r"card|result|listing", re.I),
                recursive=False,
            )
    if not job_cards:
        # Strategy 5: Broadest — any element with a job detail link
        job_cards = soup.select("[data-id]")
        if not job_cards:
            # Find all links to job detail pages and get their parent containers
            detail_links = soup.select("a[href*='/job-detail/']")
            seen_parents = set()
            card_list = []
            for link in detail_links:
                parent = link.find_parent(["div", "li", "article"])
                if parent and id(parent) not in seen_parents:
                    seen_parents.add(id(parent))
                    card_list.append(parent)
            job_cards = card_list

    logger.info(f"Found {len(job_cards)} job cards in Dice HTML")

    for card in job_cards:
        try:
            # Title
            title_el = (
                card.select_one("[data-cy='card-title'] a")
                or card.select_one("a.card-title-link")
                or card.select_one("h5 a")
                or card.select_one("a[href*='/job-detail/']")
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Job URL
            job_url = ""
            link_el = title_el if title_el and title_el.name == "a" else None
            if not link_el:
                link_el = card.select_one("a[href*='/job-detail/']")
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.dice.com{href}"
                elif href.startswith("http"):
                    job_url = href

            # Company
            company_el = (
                card.select_one("[data-cy='search-result-company-name']")
                or card.select_one("a[data-cy='card-company'] span")
                or card.select_one(".card-company a span")
                or card.select_one("a[href*='/company/'] span")
                or card.select_one(".company-name")
            )
            company = company_el.get_text(strip=True) if company_el else ""

            # Location
            location_el = (
                card.select_one("[data-cy='search-result-location']")
                or card.select_one("span.search-result-location")
                or card.select_one(".card-location")
            )
            location = location_el.get_text(strip=True) if location_el else ""

            # Salary
            salary_el = (
                card.select_one("[data-cy='card-salary']")
                or card.select_one(".card-salary")
                or card.select_one(".compensation")
            )
            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            salary_min, salary_max = _parse_salary(salary_text)

            # Date posted
            date_el = (
                card.select_one("[data-cy='card-posted-date']")
                or card.select_one(".posted-date")
                or card.select_one("span.posted")
            )
            date_posted = date_el.get_text(strip=True) if date_el else ""

            # Description snippet
            desc_el = (
                card.select_one("[data-cy='card-summary']")
                or card.select_one(".card-description")
                or card.select_one(".summary")
            )
            description = desc_el.get_text(strip=True) if desc_el else ""

            if not title or not job_url:
                continue

            jobs.append({
                "source": "dice",
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
            logger.debug(f"Error parsing Dice job card: {e}")
            continue

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Dice for jobs using Oxylabs and send to SQS.
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
                    f"Crawling Dice: role={role}, location={location}, remote={is_remote}"
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
                    f"Error crawling Dice for {role} in {location}: {e}",
                    exc_info=True,
                )
                total_errors += 1

    logger.info(f"Dice crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "dice",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
