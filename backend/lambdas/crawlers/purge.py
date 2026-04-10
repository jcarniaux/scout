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

        # Scan and delete expired jobs
        logger.info(f"Purging jobs with ttl < {current_time}")

        scan_kwargs = {
            "filter_expression": "ttl < :now",
            "expression_attribute_values": {":now": current_time},
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
        logger.info("Purging orphaned user status records")

        status_items, _ = dynamodb.scan(user_status_table)

        items_to_delete = []
        for status_item in status_items:
            job_id = status_item.get("sk", "").replace("JOB#", "")

            # Check if job exists — query by pk = "JOB#{job_hash}" (no JobHashIndex needed)
            try:
                job_items, _ = dynamodb.query(
                    jobs_table,
                    "pk = :pk",
                    {":pk": f"JOB#{job_id}"},
                )

                if not job_items:
                    # Job doesn't exist, mark status for deletion
                    items_to_delete.append({"pk": status_item["pk"], "sk": status_item["sk"]})
            except Exception as e:
                logger.warning(f"Error checking job {job_id}: {e}")
                continue

        if items_to_delete:
            dynamodb.batch_write(user_status_table, [], items_to_delete)
            statuses_deleted = len(items_to_delete)
            logger.info(f"Deleted {statuses_deleted} orphaned status records")

        return {
            "statusCode": 200,
            "jobs_deleted": jobs_deleted,
            "statuses_deleted": statuses_deleted,
        }

    except Exception as e:
        logger.error(f"Error in purge handler: {e}", exc_info=True)
        return {"statusCode": 500, "error": str(e)}
