"""
Indeed job crawler using JobSpy.
Triggered by EventBridge on a schedule (daily).
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

import boto3
from jobspy import scrape_jobs

from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
from shared.crawler_utils import extract_salary_min, extract_salary_max, meets_salary_requirement

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl Indeed for jobs and send to SQS queue for enrichment.

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
            is_remote = location_config.get("remote", False)

            try:
                logger.info(f"Crawling Indeed: role={role}, location={location}, remote={is_remote}")

                # Scrape jobs using JobSpy
                jobs_df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=role,
                    location=location,
                    distance=distance,
                    is_remote=is_remote,
                    results_wanted=50,
                    hours_old=24,  # Only last 24 hours
                    country_indeed="USA",
                )

                if jobs_df is None or len(jobs_df) == 0:
                    logger.info(f"No jobs found for {role} in {location}")
                    continue

                logger.info(f"Found {len(jobs_df)} jobs for {role} in {location}")

                # Process each job
                for idx, job in jobs_df.iterrows():
                    try:
                        salary_min = extract_salary_min(job)

                        # Skip if below salary minimum
                        if not meets_salary_requirement(salary_min, SALARY_MINIMUM):
                            logger.debug(f"Skipping {job.get('title')} - salary too low: {salary_min}")
                            continue

                        salary_max = extract_salary_max(job)

                        message = {
                            "source": "indeed",
                            "title": str(job.get("title", "")).strip(),
                            "company": str(job.get("company_name", "")).strip(),
                            "location": str(job.get("location", "")).strip(),
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "job_url": str(job.get("job_url", "")).strip(),
                            "date_posted": str(job.get("date_posted", "")).strip(),
                            "description": str(job.get("description", ""))[:2000],
                            "job_type": str(job.get("job_type", "")).strip(),
                            "crawled_at": datetime.utcnow().isoformat(),
                        }

                        # Send to SQS
                        sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message, default=str))
                        total_sent += 1

                    except Exception as e:
                        logger.error(f"Error processing job row {idx}: {e}", exc_info=True)
                        total_errors += 1
                        continue

            except Exception as e:
                logger.error(f"Error crawling Indeed for {role} in {location}: {e}", exc_info=True)
                total_errors += 1
                continue

    logger.info(f"Indeed crawl complete: {total_sent} sent, {total_errors} errors")
    return {
        "statusCode": 200,
        "source": "indeed",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
