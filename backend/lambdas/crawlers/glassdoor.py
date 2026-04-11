"""
Glassdoor job crawler using Oxylabs Web Scraper API (Realtime).

Fetches rendered Glassdoor search result pages via Oxylabs, then
parses job cards from the HTML. Glassdoor is heavily JS-rendered,
so Oxylabs' render=html is essential.

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

GLASSDOOR_BASE = "https://www.glassdoor.com/Job/jobs.htm"


def _build_search_url(role: str, location: str, distance: Optional[int], is_remote: bool) -> str:
    """
    Build a Glassdoor job search URL.

    Glassdoor URL params:
      sc.keyword  = search query
      locKeyword  = location text
      fromAge     = max days since posting (1 = last 24h)
      seniorityType = seniority filter
      remoteWorkType = remote filter (1 = remote)
      radius      = distance in miles
    """
    params = {
        "sc.keyword": role,
        "fromAge": "1",
        "sortBy": "date_desc",
    }

    if is_remote:
        params["remoteWorkType"] = "1"
        params["locKeyword"] = "United States"
    else:
        params["locKeyword"] = location
        if distance:
            params["radius"] = str(distance)

    return f"{GLASSDOOR_BASE}?{urlencode(params, quote_via=quote_plus)}"


def _parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse salary from text like "$180K - $220K (Employer est.)"."""
    if not text:
        return None, None

    matches = re.findall(r"\$?([\d,]+(?:\.\d+)?)\s*[kK]?", text)
    if not matches:
        return None, None

    salaries = []
    for m in matches:
        try:
            val = int(float(m.replace(",", "")))
            # Handle "K" suffix — values like 180 become 180000
            if val < 1000:
                val = val * 1000
            if 30000 <= val <= 1_000_000:
                salaries.append(val)
        except ValueError:
            continue

    if not salaries:
        return None, None

    return min(salaries), max(salaries) if len(salaries) > 1 else (salaries[0], None)


def _parse_jobs_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse job listings from a Glassdoor search results page.

    Glassdoor renders job cards in list items. The structure changes
    frequently, so we try multiple selector strategies.
    """
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Glassdoor modern layout — job cards with data-id
    job_cards = soup.select("li[data-test='jobListing']")
    if not job_cards:
        # Strategy 2: Cards inside job list container
        job_cards = soup.select(".JobsList_jobListItem__wjTHv")
    if not job_cards:
        # Strategy 3: Generic approach — any li with a job link
        job_cards = soup.select("li.react-job-listing")
    if not job_cards:
        # Strategy 4: Broadest — look for job title links
        job_cards = soup.select("[data-brandviews*='JOB_CARD']")
    if not job_cards:
        # Strategy 5: Fallback to ul > li with job-related content
        job_list = soup.select_one("ul.JobsList_jobsList__lqjAi") or soup.select_one(
            "[data-test='jlGrid']"
        )
        if job_list:
            job_cards = job_list.find_all("li", recursive=False)

    logger.info(f"Found {len(job_cards)} job cards in Glassdoor HTML")

    for card in job_cards:
        try:
            # Title
            title_el = (
                card.select_one("[data-test='job-title']")
                or card.select_one("a.jobTitle")
                or card.select_one("a.JobCard_jobTitle__GLyJ1")
                or card.select_one("a[href*='/job-listing/']")
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Job URL
            job_url = ""
            link_el = title_el if title_el and title_el.name == "a" else None
            if not link_el:
                link_el = card.select_one("a[href*='/job-listing/']") or card.select_one(
                    "a[href*='/partner/']"
                )
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    job_url = f"https://www.glassdoor.com{href}"
                elif href.startswith("http"):
                    job_url = href

            # Company
            company_el = (
                card.select_one("[data-test='emp-name']")
                or card.select_one(".EmployerProfile_compactEmployerName__9MGcV")
                or card.select_one(".employer-name")
            )
            company = company_el.get_text(strip=True) if company_el else ""

            # Location
            location_el = (
                card.select_one("[data-test='emp-location']")
                or card.select_one(".JobCard_location__N_iYE")
                or card.select_one(".location")
            )
            location = location_el.get_text(strip=True) if location_el else ""

            # Salary
            salary_el = (
                card.select_one("[data-test='detailSalary']")
                or card.select_one(".JobCard_salaryEstimate__QpbTW")
                or card.select_one(".salary-estimate")
            )
            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            salary_min, salary_max = _parse_salary(salary_text)

            # Date posted
            date_el = card.select_one("[data-test='job-age']") or card.select_one(
                ".JobCard_listingAge__jJsER"
            )
            date_posted = date_el.get_text(strip=True) if date_el else ""

            if not title or not job_url:
                continue

            jobs.append({
                "source": "glassdoor",
                "title": title,
                "company": company,
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "job_url": job_url,
                "date_posted": date_posted,
                "description": "",
                "job_type": "",
                "crawled_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.debug(f"Error parsing Glassdoor job card: {e}")
            continue

    return jobs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Glassdoor for jobs using Oxylabs and send to SQS.
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
                    f"Crawling Glassdoor: role={role}, location={location}, remote={is_remote}"
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
                    f"Error crawling Glassdoor for {role} in {location}: {e}",
                    exc_info=True,
                )
                total_errors += 1

    logger.info(f"Glassdoor crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "glassdoor",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
