"""
GET and PUT /user/settings API handlers.
Manage user preferences and notification settings.
"""
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

from shared.db import DynamoDBHelper
from shared.models import dynamo_serialize, dynamo_deserialize
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


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def get_settings(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handler for GET /user/settings"""
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    users_table = os.environ.get("USERS_TABLE")
    if not users_table:
        return error_response("Missing environment variables", 500)

    try:
        item = dynamodb.get_item(users_table, {"PK": f"USER#{user_sub}"})

        if not item:
            # User doesn't exist yet, return defaults
            return success_response({
                "user_id": f"USER#{user_sub}",
                "email": None,
                "daily_report": False,
                "weekly_report": False,
            })

        item = dynamo_deserialize(item)
        return success_response({
            "user_id": item.get("PK"),
            "email": item.get("email"),
            "daily_report": item.get("daily_report", False),
            "weekly_report": item.get("weekly_report", False),
        })

    except Exception as e:
        logger.error(f"Error fetching user settings: {e}", exc_info=True)
        return error_response("Error fetching settings", 500)


def put_settings(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handler for PUT /user/settings"""
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    users_table = os.environ.get("USERS_TABLE")
    if not users_table:
        return error_response("Missing environment variables", 500)

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))

        email = body.get("email", "").strip()
        daily_report = body.get("daily_report", False)
        weekly_report = body.get("weekly_report", False)

        # Validate
        if email and not validate_email(email):
            return error_response("Invalid email format", 400)

        # Build item
        item = {
            "PK": f"USER#{user_sub}",
            "user_id": f"USER#{user_sub}",
        }

        if email:
            item["email"] = email

        item["daily_report"] = bool(daily_report)
        item["weekly_report"] = bool(weekly_report)
        item["updated_at"] = datetime.utcnow().isoformat()

        # Check if this is first creation
        existing = dynamodb.get_item(users_table, {"PK": f"USER#{user_sub}"})
        if not existing:
            item["created_at"] = datetime.utcnow().isoformat()

        # Write to DynamoDB
        dynamodb.put_item(users_table, dynamo_serialize(item))

        return success_response({
            "user_id": item["PK"],
            "email": item.get("email"),
            "daily_report": item["daily_report"],
            "weekly_report": item["weekly_report"],
            "updated_at": item["updated_at"],
        })

    except json.JSONDecodeError:
        return error_response("Invalid JSON body", 400)
    except Exception as e:
        logger.error(f"Error updating user settings: {e}", exc_info=True)
        return error_response("Error updating settings", 500)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler dispatcher"""
    http_method = event.get("httpMethod", "GET").upper()

    if http_method == "PUT":
        return put_settings(event, context)
    elif http_method == "GET":
        return get_settings(event, context)
    else:
        return error_response("Method not allowed", 405)
