"""
Dice job crawler using Oxylabs Web Scraper API (Realtime).

Fetches rendered Dice search result pages via Oxylabs, then
parses job cards from the HTML using BeautifulSoup.

Dice is not supported by JobSpy, so we keep the Oxylabs approach here.
The parser uses multiple fallback strategies including a generic
link-based extractor that is resilient to DOM changes.

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
from bs4 import BeautifulSoup, Tag

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
                val = val * 2080  # Hourly to annual (40h/week x 52 weeks)
            elif val < 1000:
                val = val * 1000  # "180K" format
            if 30000 <= val <= 1_000_000:
                salaries.append(val)
        except ValueError:
            continue

    if not salaries:
        return None, None

    return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)


def _extract_text_near(element: Tag, selectors: list[str]) -> str:
    """Try each selector on an element, return first non-empty text found."""
    for sel in selectors:
        el = element.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return ""


def _find_closest_text(link: Tag, tag_names: list[str], max_depth: int = 4) -> str:
    """
    Walk up from a link element to find nearby text in sibling/parent elements.
    Useful as a generic fallback when specific selectors miss.
    """
    current = link.parent
    for _ in range(max_depth):
        if current is None:
            break
        for child in current.children:
            if isinstance(child, Tag) and child.name in tag_names and child != link:
                text = child.get_text(strip=True)
                if text and len(text) > 2:
                    return text
        current = current.parent
    return ""


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from a Dice search results page.

    Uses a two-phase approach:
      Phase 1: Try specific CSS selectors (known Dice patterns).
      Phase 2: Generic fallback — find all /job-detail/ links and extract
               data from their surrounding context. This is resilient to
               DOM class name changes.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()
    first_card_dumped = False

    # ── Phase 1: Structured card selectors (fastest, most complete) ──
    job_cards = soup.select("dhi-search-card")
    if not job_cards:
        job_cards = soup.select("[data-cy='search-card']")
    if not job_cards:
        job_cards = soup.select(".card.search-card")
    if not job_cards:
        for container_sel in ["[data-cy='search-results']", "#searchDisplay", ".search-results-container"]:
            container = soup.select_one(container_sel)
            if container:
                job_cards = container.find_all(
                    ["div", "li", "article"],
                    class_=re.compile(r"card|result|listing", re.I),
                    recursive=False,
                )
                if job_cards:
                    break

    logger.info(f"Phase 1: Found {len(job_cards)} structured job cards")

    # Title selectors to try inside each card
    title_selectors = [
        "[data-cy='card-title'] a",
        "a.card-title-link",
        "a[data-testid='job-title']",
        "h5 a",
        "h3 a",
        "h2 a",
        "a[href*='/job-detail/']",
    ]

    company_selectors = [
        "[data-cy='search-result-company-name']",
        "a[data-cy='card-company'] span",
        "[data-testid='company-name']",
        ".card-company a span",
        "a[href*='/company/'] span",
        ".company-name",
        "[class*='company']",
    ]

    location_selectors = [
        "[data-cy='search-result-location']",
        "[data-testid='location']",
        "span.search-result-location",
        ".card-location",
        "[class*='location']",
    ]

    salary_selectors = [
        "[data-cy='card-salary']",
        "[data-testid='salary']",
        ".card-salary",
        ".compensation",
        "[class*='salary']",
        "[class*='compensation']",
    ]

    for card in job_cards:
        try:
            # Dump first card HTML for debugging when no jobs are extracted
            if not first_card_dumped:
                card_html = str(card)[:3000]
                logger.info(f"First card HTML (up to 3000 chars): {card_html}")
                first_card_dumped = True

            # Title
            title = _extract_text_near(card, title_selectors)

            # Job URL — find any link to /job-detail/
            job_url = ""
            link_el = None
            for sel in title_selectors:
                link_el = card.select_one(sel)
                if link_el and link_el.name == "a" and link_el.get("href"):
                    break
            if not link_el or not link_el.get("href"):
                link_el = card.select_one("a[href*='/job-detail/']")
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.dice.com{href}"
                elif href.startswith("http"):
                    job_url = href
                # Use link text as title fallback
                if not title:
                    title = link_el.get_text(strip=True)

            # Company
            company = _extract_text_near(card, company_selectors)

            # Location
            location = _extract_text_near(card, location_selectors)

            # Salary
            salary_text = _extract_text_near(card, salary_selectors)
            salary_min, salary_max = _parse_salary(salary_text)

            if not title or not job_url:
                continue

            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            jobs.append({
                "source": "dice",
                "title": title,
                "company": company,
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "job_url": job_url,
                "date_posted": "",
                "description": "",
                "job_type": "",
                "crawled_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.debug(f"Error parsing Dice card: {e}")
            continue

    # ── Phase 2: Generic link-based fallback ──
    # If Phase 1 found nothing, find ALL /job-detail/ links and extract
    # whatever we can from surrounding context. This works even when
    # container selectors and class names change completely.
    if not jobs:
        detail_links = soup.select("a[href*='/job-detail/']")
        logger.info(f"Phase 2 fallback: Found {len(detail_links)} /job-detail/ links")

        if detail_links and not first_card_dumped:
            # Dump the first link's parent for debugging
            parent = detail_links[0].find_parent(["div", "li", "article", "section"])
            if parent:
                logger.info(f"First link parent HTML (up to 3000 chars): {str(parent)[:3000]}")

        for link in detail_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                if href.startswith("/"):
                    job_url = f"https://www.dice.com{href}"
                elif href.startswith("http"):
                    job_url = href
                else:
                    continue

                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # Title from link text
                title = link.get_text(strip=True)
                if not title:
                    # Try aria-label or title attribute
                    title = link.get("aria-label", "") or link.get("title", "")

                if not title:
                    continue

                # Walk up to find a reasonable card container
                card_container = link.find_parent(["div", "li", "article", "section"])

                company = ""
                location = ""
                salary_text = ""

                if card_container:
                    # Try specific selectors first
                    company = _extract_text_near(card_container, company_selectors)
                    location = _extract_text_near(card_container, location_selectors)
                    salary_text = _extract_text_near(card_container, salary_selectors)

                    # If specific selectors miss, try to find company from /company/ links
                    if not company:
                        company_link = card_container.select_one("a[href*='/company/']")
                        if company_link:
                            company = company_link.get_text(strip=True)

                salary_min, salary_max = _parse_salary(salary_text)

                jobs.append({
                    "source": "dice",
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "job_url": job_url,
                    "date_posted": "",
                    "description": "",
                    "job_type": "",
                    "crawled_at": datetime.utcnow().isoformat(),
                })

            except Exception as e:
                logger.debug(f"Error in Phase 2 link extraction: {e}")
                continue

    logger.info(f"Total parsed: {len(jobs)} jobs from Dice HTML")

    # If still 0, dump page diagnostics
    if not jobs:
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True)[:200] if title_tag else "(no title)"
        body = soup.find("body")
        body_text = body.get_text(separator=" ", strip=True)[:2000] if body else ""
        logger.warning(
            f"Dice: 0 jobs extracted. page_title='{page_title}', "
            f"html_size={len(html)}, detail_links={len(soup.select('a[href*=\"/job-detail/\"]'))}"
        )
        logger.warning(f"Dice body text snippet: {body_text[:1000]}")

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
