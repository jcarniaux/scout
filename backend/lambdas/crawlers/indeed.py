"""
Indeed job crawler using JobSpy.
Triggered by Step Functions as part of the daily crawl pipeline.

NOTE: Indeed has a limitation where only ONE of the following can be
used per scrape call: hours_old, job_type/is_remote, or easy_apply.
We work around this by making separate calls for time-filtered and
remote-filtered queries, then deduplicating by job URL.
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Set

import boto3
from jobspy import scrape_jobs

from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import (
    extract_salary_min,
    extract_salary_max,
    meets_salary_requirement,
    get_proxy_list,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")


def _build_scrape_kwargs(
    role: str,
    location: str,
    distance: int | None,
    is_remote: bool,
    proxies: list[str] | None,
) -> dict:
    """
    Build keyword arguments for scrape_jobs(), respecting Indeed's
    constraint that hours_old and is_remote cannot be combined.

    For non-remote searches: use hours_old=24 (last 24h).
    For remote searches:     use is_remote=True (no hours_old).
    """
    kwargs: dict = {
        "site_name": ["indeed"],
        "search_term": role,
        "location": location,
        "results_wanted": 50,
        "country_indeed": "USA",
    }

    if proxies:
        kwargs["proxies"] = proxies

    if is_remote:
        # Indeed limitation: can't combine is_remote with hours_old
        kwargs["is_remote"] = True
    else:
        kwargs["hours_old"] = 24
        if distance:
            kwargs["distance"] = distance

    return kwargs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Indeed for jobs and send to SQS queue for enrichment.
    """
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set")
        return {"statusCode": 500, "error": "Missing SQS_QUEUE_URL"}

    proxies = get_proxy_list()
    total_sent = 0
    total_errors = 0
    seen_urls: Set[str] = set()  # Deduplicate across role/location combos

    for role in ROLE_QUERIES:
        for location_config in LOCATIONS:
            location = location_config.get("location")
            distance = location_config.get("distance")
            is_remote = location_config.get("remote", False)

            try:
                logger.info(
                    f"Crawling Indeed: role={role}, location={location}, remote={is_remote}"
                )

                kwargs = _build_scrape_kwargs(role, location, distance, is_remote, proxies)
                jobs_df = scrape_jobs(**kwargs)

                if jobs_df is None or len(jobs_df) == 0:
                    logger.info(f"No jobs found for {role} in {location}")
                    continue

                logger.info(f"Found {len(jobs_df)} jobs for {role} in {location}")

                for idx, job in jobs_df.iterrows():
                    try:
                        job_url = str(job.get("job_url", "")).strip()

                        # Skip duplicates
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        salary_min = extract_salary_min(job)

                        if not meets_salary_requirement(salary_min, SALARY_MINIMUM):
                            logger.debug(
                                f"Skipping {job.get('title')} - salary too low: {salary_min}"
                            )
                            continue

                        salary_max = extract_salary_max(job)

                        message = {
                            "source": "indeed",
                            "title": str(job.get("title", "")).strip(),
                            "company": str(job.get("company_name", "")).strip(),
                            "location": str(job.get("location", "")).strip(),
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "job_url": job_url,
                            "date_posted": str(job.get("date_posted", "")).strip(),
                            "description": str(job.get("description", ""))[:2000],
                            "job_type": str(job.get("job_type", "")).strip(),
                            "crawled_at": datetime.utcnow().isoformat(),
                        }

                        sqs_client.send_message(
                            QueueUrl=queue_url,
                            MessageBody=json.dumps(message, default=str),
                        )
                        total_sent += 1

                    except Exception as e:
                        logger.error(f"Error processing job row {idx}: {e}", exc_info=True)
                        total_errors += 1
                        continue

            except Exception as e:
                logger.error(
                    f"Error crawling Indeed for {role} in {location}: {e}", exc_info=True
                )
                total_errors += 1
                continue

    logger.info(f"Indeed crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "indeed",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
