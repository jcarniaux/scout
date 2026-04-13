"""
PATCH /jobs/{jobId}/status API handler.
Update user's application status for a job.
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

from shared.db import DynamoDBHelper
from shared.models import APPLICATION_STATUSES, dynamo_serialize
from shared.response import success_response, error_response, unauthorized_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()


def get_user_sub(event: Dict[str, Any]) -> Optional[str]:
    """Extract Cognito user sub from event."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Update application status for a job.

    Expected request body:
    {
        "status": "APPLIED",
        "notes": "optional notes"
    }
    """
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    user_status_table = os.environ.get("USER_STATUS_TABLE")
    if not user_status_table:
        return error_response("Missing environment variables", 500)

    # Get jobId from path parameters
    job_id = event.get("pathParameters", {}).get("jobId")
    if not job_id:
        return error_response("Missing jobId parameter", 400)

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        status = body.get("status", "").strip().upper()
        notes = body.get("notes", "").strip()

        if not status:
            return error_response("Missing status field", 400)

        if status not in APPLICATION_STATUSES:
            return error_response(f"Invalid status. Must be one of: {', '.join(APPLICATION_STATUSES)}", 400)

        if len(notes) > 500:
            return error_response("Notes must be 500 characters or fewer", 400)

        if len(job_id) > 128:
            return error_response("Invalid jobId", 400)

        # Build item
        item = {
            "pk": f"USER#{user_sub}",
            "sk": f"JOB#{job_id}",
            "user_id": f"USER#{user_sub}",
            "job_id": f"JOB#{job_id}",
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if notes:
            item["notes"] = notes

        # Write to DynamoDB
        dynamodb.put_item(user_status_table, dynamo_serialize(item))

        return success_response({
            "user_id": item["pk"],
            "job_id": item["sk"],
            "status": status,
            "updated_at": item["updated_at"],
            "notes": notes,
        })

    except json.JSONDecodeError:
        return error_response("Invalid JSON body", 400)
    except Exception as e:
        logger.error(f"Error updating status for job {job_id}: {e}", exc_info=True)
        return error_response("Error updating status", 500)
