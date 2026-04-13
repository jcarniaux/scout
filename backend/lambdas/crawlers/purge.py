"""
Job and status cleanup Lambda.
Removes expired jobs and orphaned user status records.
Triggered by EventBridge on a schedule (daily).
"""
import logging
import os
import time
from typing import Dict, Any

from shared.db import DynamoDBHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Clean up expired jobs and orphaned status records.

    Args:
        event: EventBridge event
        context: Lambda context

    Returns:
        Status dict
    """
    jobs_table = os.environ.get("JOBS_TABLE")
    user_status_table = os.environ.get("USER_STATUS_TABLE")

    if not jobs_table or not user_status_table:
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "error": "Missing environment variables"}

    try:
        current_time = int(time.time())
        jobs_deleted = 0
        statuses_deleted = 0
        source_purged = 0

        # ── Optional: purge all jobs from specific sources ──
        # Invoke with {"purge_sources": ["ziprecruiter", "glassdoor"]}
        # to remove all jobs from disabled crawlers.
        purge_sources = event.get("purge_sources")
        if purge_sources:
            logger.info(f"Purging all jobs from sources: {purge_sources}")
            last_key = None
            while True:
                scan_kwargs_src = {
                    "filter_expression": "#src IN ({})".format(
                        ", ".join(f":s{i}" for i in range(len(purge_sources)))
                    ),
                    "expression_attribute_values": {
                        f":s{i}": s for i, s in enumerate(purge_sources)
                    },
                    "expression_attribute_names": {"#src": "source"},
                }
                if last_key:
                    scan_kwargs_src["exclusive_start_key"] = last_key

                items, last_key = dynamodb.scan(jobs_table, **scan_kwargs_src)
                if items:
                    keys_to_delete = [{"pk": item["pk"], "sk": item["sk"]} for item in items]
                    dynamodb.batch_write(jobs_table, [], keys_to_delete)
                    source_purged += len(keys_to_delete)
                    logger.info(f"Deleted {len(keys_to_delete)} jobs from {purge_sources}")

                if not last_key:
                    break

            logger.info(f"Total source-purged: {source_purged} jobs")

        # ── Purge TTL-expired jobs ──
        logger.info(f"Purging jobs with ttl < {current_time}")

        scan_kwargs = {
            "filter_expression": "#ttl < :now",
            "expression_attribute_values": {":now": current_time},
            "expression_attribute_names": {"#ttl": "ttl"},
        }

        while True:
            items, last_key = dynamodb.scan(jobs_table, **scan_kwargs)

            if not items:
                break

            # Delete in batches
            items_to_delete = [{"pk": item["pk"], "sk": item["sk"]} for item in items]

            dynamodb.batch_write(jobs_table, [], items_to_delete)
            jobs_deleted += len(items_to_delete)
            logger.info(f"Deleted {len(items_to_delete)} expired jobs")

            if not last_key:
                break

            scan_kwargs["exclusive_start_key"] = last_key

        logger.info(f"Total jobs deleted: {jobs_deleted}")

        # Scan and delete orphaned user status records
        # (where the referenced job no longer exists)
        #
        # Strategy: scan the jobs table once to build a set of existing job PKs,
        # then scan status records and check membership in-memory.
        # This is 2 scans instead of N+1 queries.
        logger.info("Purging orphaned user status records")

        # 1. Build set of existing job PKs from a full scan (projection = pk only)
        existing_job_pks: set = set()
        last_key = None
        while True:
            items, last_key = dynamodb.scan(
                jobs_table,
                projection_expression="#pk",
                expression_attribute_names={"#pk": "pk"},
                exclusive_start_key=last_key,
            )
            for item in items:
                existing_job_pks.add(item.get("pk", ""))
            if not last_key:
                break

        logger.info(f"Found {len(existing_job_pks)} existing job PKs")

        # 2. Scan all status records and find orphans
        items_to_delete = []
        last_key = None
        while True:
            status_items, last_key = dynamodb.scan(user_status_table)
            for status_item in status_items:
                # status sk is "JOB#{job_hash}" — the corresponding jobs pk is the same
                job_pk = status_item.get("sk", "")
                if job_pk and job_pk not in existing_job_pks:
                    items_to_delete.append({"pk": status_item["pk"], "sk": status_item["sk"]})
            if not last_key:
                break

        if items_to_delete:
            dynamodb.batch_write(user_status_table, [], items_to_delete)
            statuses_deleted = len(items_to_delete)
            logger.info(f"Deleted {statuses_deleted} orphaned status records")

        return {
            "statusCode": 200,
            "source_purged": source_purged,
            "jobs_deleted": jobs_deleted,
            "statuses_deleted": statuses_deleted,
        }

    except Exception as e:
        logger.error(f"Error in purge handler: {e}", exc_info=True)
        return {"statusCode": 500, "error": str(e)}
