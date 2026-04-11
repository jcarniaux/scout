"""
Crawler diagnostic Lambda — tests each crawler's pipeline and reports
exactly where failures occur.

Architecture:
  - Indeed, Glassdoor, ZipRecruiter: Use JobSpy (same as LinkedIn)
  - Dice: Uses Oxylabs + BeautifulSoup (not supported by JobSpy)

Deploy alongside the other crawlers and invoke manually:
    aws lambda invoke --function-name scout-crawl-diagnose out.json
    cat out.json | python -m json.tool

Test individual sources:
    aws lambda invoke --function-name scout-crawl-diagnose \
      --payload '{"sources": ["dice"]}' out.json

Does NOT write to SQS — read-only diagnostics.
"""
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict

from shared.models import LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import (
    get_scraper_secrets,
    get_proxy_list,
    extract_salary_min,
    meets_salary_requirement,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TEST_ROLE = "Security Engineer"
TEST_LOCATION = LOCATIONS[0]  # Atlanta, GA


def _test_jobspy_source(site_name: str, jobspy_name: str, role: str, location_config: dict) -> Dict[str, Any]:
    """Test a JobSpy-based crawler (Indeed, Glassdoor, ZipRecruiter)."""
    from jobspy import scrape_jobs

    report: Dict[str, Any] = {
        "source": site_name,
        "engine": "jobspy",
        "timestamp": datetime.utcnow().isoformat(),
    }

    location = location_config["location"]
    distance = location_config.get("distance")
    is_remote = location_config.get("remote", False)

    kwargs: dict = {
        "site_name": [jobspy_name],
        "search_term": role,
        "location": location,
        "is_remote": is_remote,
        "results_wanted": 10,  # Small sample for diagnostics
        "hours_old": 24,
    }
    if site_name == "indeed":
        kwargs["country_indeed"] = "USA"
    if distance:
        kwargs["distance"] = distance

    proxies = get_proxy_list()
    if proxies:
        kwargs["proxies"] = proxies

    start = time.time()
    try:
        jobs_df = scrape_jobs(**kwargs)
        elapsed = round(time.time() - start, 1)
        report["fetch_seconds"] = elapsed

        if jobs_df is None or len(jobs_df) == 0:
            report["status"] = "NO_RESULTS"
            report["jobs_found"] = 0
            return report

        report["status"] = "OK"
        report["jobs_found"] = len(jobs_df)

        # Check salary data availability
        jobs_with_salary = 0
        jobs_meeting_salary = 0
        for _, job in jobs_df.iterrows():
            sal_min = extract_salary_min(job)
            if sal_min is not None:
                jobs_with_salary += 1
            if meets_salary_requirement(sal_min, SALARY_MINIMUM):
                jobs_meeting_salary += 1

        report["jobs_with_salary"] = jobs_with_salary
        report["jobs_meeting_salary_filter"] = jobs_meeting_salary

        # Sample job
        first = jobs_df.iloc[0]
        report["sample_job"] = {
            "title": str(first.get("title", "")),
            "company": str(first.get("company_name", "")),
            "location": str(first.get("location", "")),
            "job_url": str(first.get("job_url", "")),
            "date_posted": str(first.get("date_posted", "")),
        }

        # List available columns for debugging
        report["dataframe_columns"] = list(jobs_df.columns)

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        report["fetch_seconds"] = elapsed
        report["status"] = f"ERROR: {type(e).__name__}: {str(e)[:500]}"
        report["jobs_found"] = 0

    return report


def _test_oxylabs_source(source: str, role: str, location_config: dict) -> Dict[str, Any]:
    """Test an Oxylabs-based crawler (Dice, Glassdoor, ZipRecruiter)."""
    # Dynamic import based on source
    if source == "dice":
        from crawlers.dice import _build_search_url, _parse_jobs_from_html
    elif source == "glassdoor":
        from crawlers.glassdoor import _build_search_url, _parse_jobs_from_html
    elif source == "ziprecruiter":
        from crawlers.ziprecruiter import _build_search_url, _parse_jobs_from_html
    else:
        return {"error": f"Unknown Oxylabs source: {source}"}

    from shared.oxylabs_client import OxylabsClient

    report: Dict[str, Any] = {
        "source": source,
        "engine": "oxylabs+beautifulsoup",
        "timestamp": datetime.utcnow().isoformat(),
    }

    location = location_config["location"]
    distance = location_config.get("distance")
    is_remote = location_config.get("remote", False)

    # Test Oxylabs connectivity
    try:
        client = OxylabsClient()
        report["oxylabs_init"] = "OK"
    except RuntimeError as e:
        report["oxylabs_init"] = f"FAILED: {e}"
        report["status"] = "OXYLABS_AUTH_FAILED"
        return report

    url = _build_search_url(role, location, distance, is_remote)
    report["test_url"] = url

    start = time.time()
    html = client.fetch_page(url)
    elapsed = round(time.time() - start, 1)
    report["fetch_seconds"] = elapsed

    if not html:
        report["status"] = "FETCH_FAILED"
        report["jobs_found"] = 0
        return report

    report["html_size"] = len(html)

    # Parse
    jobs = _parse_jobs_from_html(html)
    report["jobs_found"] = len(jobs)

    if jobs:
        report["status"] = "OK"
        report["sample_job"] = jobs[0]

        jobs_with_salary = sum(1 for j in jobs if j.get("salary_min") is not None)
        jobs_meeting_salary = sum(
            1 for j in jobs if meets_salary_requirement(j.get("salary_min"), SALARY_MINIMUM)
        )
        report["jobs_with_salary"] = jobs_with_salary
        report["jobs_meeting_salary_filter"] = jobs_meeting_salary
    else:
        # Diagnostics for empty parse
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        report["page_title"] = title_tag.get_text(strip=True)[:200] if title_tag else "(no title)"

        # Count /job-detail/ links
        detail_links = soup.select("a[href*='/job-detail/']")
        report["detail_links_count"] = len(detail_links)

        if detail_links:
            report["status"] = "PARSE_FAILED (links found but extraction failed)"
            # Show first link context
            first_parent = detail_links[0].find_parent(["div", "li", "article"])
            if first_parent:
                report["first_link_parent_html"] = str(first_parent)[:2000]
        else:
            report["status"] = "NO_JOB_LINKS (page may be blocked or empty)"
            body = soup.find("body")
            if body:
                report["body_text_snippet"] = body.get_text(separator=" ", strip=True)[:1500]

    return report


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Run diagnostics on all crawlers.

    Invoke with optional event body:
      {"sources": ["indeed"]}     — test only Indeed
      {"sources": ["dice"]}       — test only Dice
      {"role": "Cloud Architect"} — use a different test role
      {}                          — test all 4
    """
    requested_sources = event.get("sources", ["indeed", "dice"])
    role = event.get("role", TEST_ROLE)
    loc = TEST_LOCATION

    report: Dict[str, Any] = {"diagnostics_ran_at": datetime.utcnow().isoformat()}

    # Check secrets
    try:
        secrets = get_scraper_secrets()
        report["secrets"] = {
            "oxylabs_username_present": bool(secrets.get("oxylabs_username")),
            "oxylabs_password_present": bool(secrets.get("oxylabs_password")),
            "scraping_proxy_present": bool(secrets.get("scraping_proxy")),
        }
    except Exception as e:
        report["secrets"] = {"error": str(e)}

    # Map sources to their test functions
    # Indeed: JobSpy (no rate limiting, works well)
    # Glassdoor, ZipRecruiter, Dice: Oxylabs (Cloudflare blocks JobSpy)
    jobspy_sources = {
        "indeed": ("indeed", "indeed"),
    }

    oxylabs_sources = {"dice"}

    source_reports = {}
    for source in requested_sources:
        try:
            if source in jobspy_sources:
                name, jobspy_name = jobspy_sources[source]
                logger.info(f"Diagnosing {name} via JobSpy...")
                source_reports[source] = _test_jobspy_source(name, jobspy_name, role, loc)
            elif source in oxylabs_sources:
                logger.info(f"Diagnosing {source} via Oxylabs...")
                source_reports[source] = _test_oxylabs_source(source, role, loc)
            else:
                source_reports[source] = {"error": f"Unknown source: {source}"}
        except Exception as e:
            logger.error(f"Diagnostic failed for {source}: {e}", exc_info=True)
            source_reports[source] = {"error": str(e)}

    report["sources"] = source_reports

    # Summary
    summary = {}
    for src, data in source_reports.items():
        status = data.get("status", "UNKNOWN")
        jobs = data.get("jobs_found", 0)
        meeting = data.get("jobs_meeting_salary_filter", 0)
        if "OK" in status:
            summary[src] = f"OK ({jobs} found, {meeting} pass salary filter)"
        else:
            summary[src] = status
    report["summary"] = summary

    logger.info(f"Diagnostic summary: {json.dumps(summary)}")
    return {"statusCode": 200, "body": json.dumps(report, default=str, indent=2)}
