"""
Indeed job crawler using JobSpy.

Migrated from Oxylabs+BeautifulSoup to JobSpy to eliminate CSS selector
rot. JobSpy handles Indeed's DOM changes, anti-bot protections, and
data extraction internally — same library that powers the LinkedIn crawler.

Indeed reportedly has no rate limiting, so proxies are optional.

Triggered by Step Functions as part of the daily crawl pipeline.
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Set

import boto3
from jobspy import scrape_jobs

from shared.metrics import emit_metric
from shared.search_config import load_search_config
from shared.crawler_utils import (
    extract_salary_min,
    extract_salary_max,
    meets_salary_requirement,
    get_proxy_list,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Indeed for jobs using JobSpy and send to SQS queue for enrichment.
    """
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set")
        return {"statusCode": 500, "error": "Missing SQS_QUEUE_URL"}

    config = load_search_config()
    role_queries = config["role_queries"]
    locations = config["locations"]
    salary_minimum = config["salary_minimum"]

    proxies = get_proxy_list()
    total_sent = 0
    total_errors = 0
    seen_urls: Set[str] = set()

    for role in role_queries:
        for location_config in locations:
            location = location_config.get("location")
            distance = location_config.get("distance")
            is_remote = location_config.get("remote", False)

            try:
                logger.info(
                    f"Crawling Indeed: role={role}, location={location}, remote={is_remote}"
                )

                kwargs: dict = {
                    "site_name": ["indeed"],
                    "search_term": role,
                    "location": location,
                    "is_remote": is_remote,
                    "results_wanted": 50,
                    "hours_old": 24,
                    "country_indeed": "USA",
                }

                if distance:
                    kwargs["distance"] = distance

                if proxies:
                    kwargs["proxies"] = proxies

                jobs_df = scrape_jobs(**kwargs)

                if jobs_df is None or len(jobs_df) == 0:
                    logger.info(f"No jobs found for {role} in {location}")
                    continue

                logger.info(f"Found {len(jobs_df)} jobs for {role} in {location}")

                for idx, job in jobs_df.iterrows():
                    try:
                        job_url = str(job.get("job_url", "")).strip()

                        if not job_url or job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        salary_min = extract_salary_min(job)

                        if not meets_salary_requirement(salary_min, salary_minimum):
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

    emit_metric("Scout/Crawlers", "JobsSent", total_sent, source="indeed")
    emit_metric("Scout/Crawlers", "Errors", total_errors, source="indeed")

    return {
        "statusCode": 200,
        "source": "indeed",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
