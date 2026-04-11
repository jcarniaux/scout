"""
ZipRecruiter job crawler using Oxylabs Web Scraper API (Realtime).

Uses Oxylabs for fetching because ZipRecruiter's Cloudflare WAF blocks
direct requests (JobSpy gets 403). Oxylabs handles anti-bot on their
infrastructure.

Parser uses a two-phase approach for resilience against DOM changes:
  Phase 1: Specific CSS selectors for known ZipRecruiter patterns
  Phase 2: Generic link-based fallback using /jobs/ URL patterns

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

ZIPRECRUITER_BASE = "https://www.ziprecruiter.com/jobs-search"


def _build_search_url(
    role: str, location: str, distance: Optional[int], is_remote: bool
) -> str:
    """Build a ZipRecruiter search URL."""
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
    """Parse salary from text like '$180,000 - $220,000 a year'."""
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


def _extract_text(element: Tag, selectors: list[str]) -> str:
    """Try each selector on an element, return first non-empty text."""
    for sel in selectors:
        el = element.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return ""


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from a ZipRecruiter search results page.

    Two-phase approach:
      Phase 1: Specific CSS selectors (known ZipRecruiter patterns)
      Phase 2: Generic fallback — find job links and extract from context
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()
    first_card_dumped = False

    # ── Phase 1: Structured card selectors ──
    job_cards = soup.select("article.job_result")
    if not job_cards:
        job_cards = soup.select("[data-testid='job-card']")
    if not job_cards:
        job_cards = soup.select(".jobList > article") or soup.select(
            ".job_results_list > div"
        )
    if not job_cards:
        job_cards = soup.select("[data-job-id]")
    if not job_cards:
        container = soup.select_one("#job_results_list") or soup.select_one(
            ".job_results"
        )
        if container:
            job_cards = container.find_all(
                ["article", "div", "li"], class_=re.compile(r"job"), recursive=False
            )

    logger.info(f"Phase 1: Found {len(job_cards)} structured job cards")

    title_selectors = [
        "h2.job_title a",
        ".job_title a",
        "[data-testid='job-title'] a",
        "a.job_link",
        "h2 a",
        "h3 a",
        "a[href*='/jobs/']",
        "a[href*='/job/']",
    ]

    company_selectors = [
        "[data-testid='company-name']",
        ".hiring_company .t_org_link",
        "a.t_org_link",
        ".company_name",
        "[class*='company']",
        "a[href*='/employer/']",
    ]

    location_selectors = [
        "[data-testid='job-location']",
        ".job_location",
        ".location",
        "[class*='location']",
    ]

    salary_selectors = [
        "[data-testid='salary']",
        ".job_salary",
        ".salary",
        "[class*='salary']",
        "[class*='compensation']",
    ]

    for card in job_cards:
        try:
            if not first_card_dumped:
                logger.info(f"First card HTML (up to 3000 chars): {str(card)[:3000]}")
                first_card_dumped = True

            title = _extract_text(card, title_selectors)

            # Job URL
            job_url = ""
            link_el = None
            for sel in title_selectors:
                link_el = card.select_one(sel)
                if link_el and link_el.name == "a" and link_el.get("href"):
                    break
            if not link_el or not link_el.get("href"):
                link_el = card.select_one("a[href*='/jobs/']") or card.select_one(
                    "a[href*='/job/']"
                )
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.ziprecruiter.com{href}"
                elif href.startswith("http"):
                    job_url = href
                if not title:
                    title = link_el.get_text(strip=True)

            company = _extract_text(card, company_selectors)
            location = _extract_text(card, location_selectors)
            salary_text = _extract_text(card, salary_selectors)
            salary_min, salary_max = _parse_salary(salary_text)

            if not title or not job_url:
                continue
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            jobs.append({
                "source": "ziprecruiter",
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
            logger.debug(f"Error parsing ZipRecruiter card: {e}")
            continue

    # ── Phase 2: Generic link-based fallback ──
    if not jobs:
        # ZipRecruiter job links typically match /jobs/ or /job/ patterns
        job_links = soup.select("a[href*='/jobs/']")
        if not job_links:
            job_links = soup.select("a[href*='/job/']")
        # Filter out navigation/category links — real job links are longer
        job_links = [
            a for a in job_links
            if a.get("href") and len(a.get("href", "")) > 30
        ]

        logger.info(f"Phase 2 fallback: Found {len(job_links)} job links")

        if job_links and not first_card_dumped:
            parent = job_links[0].find_parent(["div", "li", "article", "section"])
            if parent:
                logger.info(
                    f"First link parent HTML (up to 3000 chars): {str(parent)[:3000]}"
                )

        for link in job_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue
                if href.startswith("/"):
                    job_url = f"https://www.ziprecruiter.com{href}"
                elif href.startswith("http"):
                    job_url = href
                else:
                    continue

                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = link.get_text(strip=True)
                if not title:
                    title = link.get("aria-label", "") or link.get("title", "")
                if not title:
                    continue

                card_container = link.find_parent(["div", "li", "article", "section"])
                company = ""
                location = ""
                salary_text = ""
                if card_container:
                    company = _extract_text(card_container, company_selectors)
                    location = _extract_text(card_container, location_selectors)
                    salary_text = _extract_text(card_container, salary_selectors)
                    if not company:
                        emp_link = card_container.select_one("a[href*='/employer/']")
                        if emp_link:
                            company = emp_link.get_text(strip=True)

                salary_min, salary_max = _parse_salary(salary_text)

                jobs.append({
                    "source": "ziprecruiter",
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

    logger.info(f"Total parsed: {len(jobs)} jobs from ZipRecruiter HTML")

    if not jobs:
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True)[:200] if title_tag else "(no title)"
        body = soup.find("body")
        body_text = body.get_text(separator=" ", strip=True)[:2000] if body else ""
        logger.warning(
            f"ZipRecruiter: 0 jobs extracted. page_title='{page_title}', "
            f"html_size={len(html)}"
        )
        logger.warning(f"ZipRecruiter body text snippet: {body_text[:1000]}")

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Crawl ZipRecruiter for jobs using Oxylabs and send to SQS."""
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
