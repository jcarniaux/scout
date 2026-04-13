"""
LinkedIn job crawler using JobSpy.
Triggered by Step Functions as part of the daily crawl pipeline.

LinkedIn's guest API is more lenient than Indeed/Glassdoor, but still
benefits from proxy rotation to avoid rate limiting on high-volume
scrapes (10+ role queries × 2 locations = 20+ requests).

Contract type strategy:
  JobSpy does not return job_type or description in LinkedIn search results
  (both come back as None/empty). To populate contract_type reliably we run
  two separate searches per role+location using JobSpy's job_type filter:
    - JobType.FULLTIME  → contract_type = "permanent"
    - JobType.CONTRACT  → contract_type = "contract"
  Jobs that appear in both searches are de-duplicated by the enrichment
  handler; the first write wins (condition_expression="attribute_not_exists").
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Set, Optional

import boto3
from jobspy import scrape_jobs, JobType

from shared.metrics import emit_metric
from shared.search_config import load_search_config
from shared.crawler_utils import (
    clean_field,
    extract_salary_min,
    extract_salary_max,
    meets_salary_requirement,
    get_proxy_list,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client("sqs")

# Each entry: (JobSpy JobType filter, contract_type label to stamp on the message)
# None means no filter — used as a catch-all for any job type not covered above.
CONTRACT_TYPE_SEARCHES: list = [
    (JobType.FULLTIME,  "permanent"),
    (JobType.CONTRACT,  "contract"),
    (None,              None),        # unfiltered pass — freelance / unlabelled roles
]


def _scrape(
    role: str,
    location: Optional[str],
    is_remote: bool,
    distance: Optional[int],
    job_type_filter: Optional[JobType],
    proxies: Optional[list],
) -> Any:
    """Run a single JobSpy scrape and return the DataFrame (or None)."""
    kwargs: dict = {
        "site_name": ["linkedin"],
        "search_term": role,
        "location": location,
        "is_remote": is_remote,
        "results_wanted": 25,   # reduced per search since we now run 3 passes
        "hours_old": 24,
    }
    if distance:
        kwargs["distance"] = distance
    if proxies:
        kwargs["proxies"] = proxies
    if job_type_filter is not None:
        kwargs["job_type"] = job_type_filter

    return scrape_jobs(**kwargs)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Crawl LinkedIn for jobs and send to SQS queue for enrichment.
    Runs three searches per role+location: fulltime, contract, and unfiltered.
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

            for job_type_filter, contract_type_label in CONTRACT_TYPE_SEARCHES:
                filter_label = job_type_filter.value[0] if job_type_filter else "unfiltered"
                try:
                    logger.info(
                        f"Crawling LinkedIn: role={role}, location={location}, "
                        f"remote={is_remote}, job_type={filter_label}"
                    )

                    jobs_df = _scrape(role, location, is_remote, distance, job_type_filter, proxies)

                    if jobs_df is None or len(jobs_df) == 0:
                        logger.info(
                            f"No jobs found for {role} in {location} ({filter_label})"
                        )
                        continue

                    logger.info(
                        f"Found {len(jobs_df)} jobs for {role} in {location} ({filter_label})"
                    )

                    # Log sample row once per crawl for debugging column drift
                    if len(jobs_df) > 0:
                        first = jobs_df.iloc[0]
                        logger.info(
                            f"Sample row — company={first.get('company')!r}, "
                            f"job_type={first.get('job_type')!r}, "
                            f"title={first.get('title')!r}"
                        )

                    for idx, job in jobs_df.iterrows():
                        try:
                            job_url = str(job.get("job_url", "")).strip()

                            if job_url in seen_urls:
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
                                "source": "linkedin",
                                "title": clean_field(job.get("title")),
                                "company": clean_field(job.get("company") or job.get("company_name")),
                                "location": clean_field(job.get("location")),
                                "salary_min": salary_min,
                                "salary_max": salary_max,
                                "job_url": job_url,
                                "date_posted": clean_field(job.get("date_posted")),
                                "description": clean_field(job.get("description"))[:2000],
                                "job_type": clean_field(job.get("job_type")),
                                # Stamp contract_type from the search filter — more reliable
                                # than trying to parse it from description (which is empty
                                # in LinkedIn search results).
                                "contract_type": contract_type_label,
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
                        f"Error crawling LinkedIn for {role} in {location} "
                        f"({filter_label}): {e}",
                        exc_info=True,
                    )
                    total_errors += 1
                    continue

    logger.info(f"LinkedIn crawl complete: {total_sent} sent, {total_errors} errors")

    emit_metric("Scout/Crawlers", "JobsSent", total_sent, source="linkedin")
    emit_metric("Scout/Crawlers", "Errors", total_errors, source="linkedin")

    return {
        "statusCode": 200,
        "source": "linkedin",
        "jobs_sent": total_sent,
        "errors": total_errors,
    }
