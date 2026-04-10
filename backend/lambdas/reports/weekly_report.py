"""
Weekly report Lambda.
Sends weekly application pipeline summary to subscribed users.
Triggered by EventBridge on a schedule (weekly).
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any

import boto3

from shared.db import DynamoDBHelper
from shared.models import dynamo_deserialize
from shared.email_templates import weekly_report_email

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
ses_client = boto3.client("ses")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Send weekly application pipeline summary to subscribed users.

    Args:
        event: EventBridge event
        context: Lambda context

    Returns:
        Status dict
    """
    users_table = os.environ.get("USERS_TABLE")
    user_status_table = os.environ.get("USER_STATUS_TABLE")
    jobs_table = os.environ.get("JOBS_TABLE")
    ses_sender_email = os.environ.get("SES_SENDER_EMAIL")

    if not all([users_table, user_status_table, jobs_table, ses_sender_email]):
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "error": "Missing environment variables"}

    try:
        # Get users with weekly_report enabled
        all_users, _ = dynamodb.scan(users_table)
        all_users = [dynamo_deserialize(u) for u in all_users]
        subscribed_users = [u for u in all_users if u.get("email") and u.get("weekly_report")]

        logger.info(f"Sending weekly report to {len(subscribed_users)} users")

        # Calculate date range for new jobs (last 7 days)
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

        emails_sent = 0

        for user in subscribed_users:
            try:
                user_id = user.get("pk")
                email = user.get("email")

                if not email or not user_id:
                    continue

                # Get user's application statuses
                statuses, _ = dynamodb.query(
                    user_status_table,
                    "pk = :pk",
                    {":pk": user_id},
                )

                # Group by status
                status_groups = {}
                for status_item in statuses:
                    status_item = dynamo_deserialize(status_item)
                    status = status_item.get("status", "NOT_APPLIED")
                    job_id = status_item.get("sk", "").replace("JOB#", "")

                    if status not in status_groups:
                        status_groups[status] = []

                    # Fetch job details
                    try:
                        job_items, _ = dynamodb.query(
                            jobs_table,
                            "pk = :pk",
                            {":pk": f"JOB#{job_id}"},
                        )
                        if job_items:
                            job = dynamo_deserialize(job_items[0])
                            status_groups[status].append(job)
                    except Exception as e:
                        logger.warning(f"Error fetching job {job_id}: {e}")
                        continue

                # Count new jobs this week
                new_jobs, _ = dynamodb.query(
                    jobs_table,
                    "gsi1pk = :pk AND postedDate >= :start",
                    {":pk": "JOB", ":start": week_ago},
                    index_name="DateIndex",
                )
                new_jobs_count = len(new_jobs)

                # Build and send email
                date_str = datetime.utcnow().strftime("%B %d, %Y")
                html_body = weekly_report_email(status_groups, new_jobs_count, date_str)

                ses_client.send_email(
                    Source=ses_sender_email,
                    Destination={"ToAddresses": [email]},
                    Message={
                        "Subject": {"Data": f"Scout Weekly Status — {date_str}"},
                        "Body": {"Html": {"Data": html_body}},
                    },
                )

                emails_sent += 1
                logger.info(f"Sent weekly report to {email}")

            except Exception as e:
                logger.error(f"Error sending report to {user.get('email')}: {e}", exc_info=True)
                continue

        return {
            "statusCode": 200,
            "emails_sent": emails_sent,
        }

    except Exception as e:
        logger.error(f"Error in weekly report handler: {e}", exc_info=True)
        return {"statusCode": 500, "error": str(e)}
