"""
Daily report Lambda.
Sends daily summary email to users who opted in.
Triggered by EventBridge on a schedule (daily).
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any

import boto3

from shared.db import DynamoDBHelper
from shared.models import dynamo_deserialize
from shared.email_templates import daily_report_email

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
ses_client = boto3.client("ses")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Send daily job report to subscribed users.

    Args:
        event: EventBridge event
        context: Lambda context

    Returns:
        Status dict
    """
    jobs_table = os.environ.get("JOBS_TABLE")
    users_table = os.environ.get("USERS_TABLE")
    ses_sender_email = os.environ.get("SES_SENDER_EMAIL")

    if not jobs_table or not users_table or not ses_sender_email:
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "error": "Missing environment variables"}

    try:
        # Get jobs from last 24 hours using DateIndex (gsi1pk + postedDate)
        start_date = (datetime.utcnow() - timedelta(hours=24)).date().isoformat()

        all_jobs: list = []
        last_key = None
        while True:
            items, last_key = dynamodb.query(
                jobs_table,
                "gsi1pk = :pk AND postedDate >= :start",
                {":pk": "JOB", ":start": start_date},
                index_name="DateIndex",
                scan_index_forward=False,
                exclusive_start_key=last_key,
            )
            all_jobs.extend(items)
            if not last_key:
                break

        jobs = all_jobs

        if not jobs:
            logger.info("No new jobs in the last 24 hours")
            return {"statusCode": 200, "emails_sent": 0, "jobs_found": 0}

        jobs = [dynamo_deserialize(job) for job in jobs]
        logger.info(f"Found {len(jobs)} new jobs in the last 24 hours")

        # Get users with daily_report enabled
        users, _ = dynamodb.scan(
            users_table,
            "daily_report = :true",
            {":true": True},
        )

        users = [dynamo_deserialize(user) for user in users]
        users = [u for u in users if u.get("email") and u.get("daily_report")]

        logger.info(f"Sending report to {len(users)} users")

        # Send email to each user
        emails_sent = 0
        for user in users:
            try:
                email = user.get("email")
                if not email:
                    continue

                # Build email
                date_str = datetime.utcnow().strftime("%B %d, %Y")
                html_body = daily_report_email(jobs, date_str)

                # Send via SES
                ses_client.send_email(
                    Source=ses_sender_email,
                    Destination={"ToAddresses": [email]},
                    Message={
                        "Subject": {"Data": f"Scout Daily Report — {len(jobs)} New Postings"},
                        "Body": {"Html": {"Data": html_body}},
                    },
                )

                emails_sent += 1
                logger.info(f"Sent daily report to {email}")

            except Exception as e:
                logger.error(f"Error sending report to {user.get('email')}: {e}")
                continue

        return {
            "statusCode": 200,
            "emails_sent": emails_sent,
            "jobs_found": len(jobs),
        }

    except Exception as e:
        logger.error(f"Error in daily report handler: {e}", exc_info=True)
        return {"statusCode": 500, "error": "Internal error in daily report"}
