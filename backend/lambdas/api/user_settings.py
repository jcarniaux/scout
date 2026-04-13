"""
User settings and resume management API handlers.

Routes (all require Cognito auth):
  GET    /user/settings            — fetch preferences + resume status
  PUT    /user/settings            — update preferences
  POST   /user/resume/upload-url   — generate a short-lived S3 pre-signed PUT URL
  DELETE /user/resume              — delete resume from S3 and clear DynamoDB fields
"""
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional

import boto3

from shared.db import DynamoDBHelper
from shared.models import dynamo_deserialize
from shared.response import success_response, error_response, unauthorized_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
_s3 = boto3.client("s3")


def get_user_sub(event: Dict[str, Any]) -> Optional[str]:
    """Extract Cognito user sub from event."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def get_cognito_email(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract the verified email from Cognito JWT claims.

    Because the user pool uses username_attributes = ["email"],
    the email claim is always present in the ID token and is the
    authoritative address for reports.
    """
    try:
        return event["requestContext"]["authorizer"]["claims"]["email"]
    except (KeyError, TypeError):
        return None


def _serialize_search_prefs(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract search preferences from a DynamoDB user item."""
    return {
        "role_queries": item.get("role_queries", []),
        "locations": item.get("search_locations", []),
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
    }


def get_settings(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handler for GET /user/settings"""
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    cognito_email = get_cognito_email(event)

    users_table = os.environ.get("USERS_TABLE")
    if not users_table:
        return error_response("Missing environment variables", 500)

    try:
        item = dynamodb.get_item(users_table, {"pk": f"USER#{user_sub}"})

        if not item:
            # User doesn't exist yet, return defaults with Cognito email
            return success_response({
                "user_id": f"USER#{user_sub}",
                "email": cognito_email,
                "daily_report": False,
                "weekly_report": False,
                "search_preferences": {
                    "role_queries": [],
                    "locations": [],
                    "salary_min": None,
                    "salary_max": None,
                },
            })

        item = dynamo_deserialize(item)
        return success_response({
            "user_id": item.get("pk"),
            # Always return the Cognito email — it's the authoritative address
            "email": cognito_email or item.get("email"),
            "daily_report": item.get("daily_report", False),
            "weekly_report": item.get("weekly_report", False),
            "search_preferences": _serialize_search_prefs(item),
            # Resume fields (None until a resume is uploaded and parsed)
            "resume_status":   item.get("resume_status"),    # None | "processing" | "ready" | "error"
            "resume_filename": item.get("resume_filename"),
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

    cognito_email = get_cognito_email(event)

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))

        daily_report = body.get("daily_report", False)
        weekly_report = body.get("weekly_report", False)
        search_prefs = body.get("search_preferences", {})

        # Validate search preferences
        role_queries = search_prefs.get("role_queries", [])
        if not isinstance(role_queries, list):
            return error_response("role_queries must be a list", 400)
        if len(role_queries) > 50:
            return error_response("Maximum 50 role queries allowed", 400)
        role_queries = [r.strip()[:200] for r in role_queries if isinstance(r, str) and r.strip()]

        locations = search_prefs.get("locations", [])
        if not isinstance(locations, list):
            return error_response("locations must be a list", 400)
        if len(locations) > 50:
            return error_response("Maximum 50 locations allowed", 400)
        # Each location: {"location": str, "distance": int|None, "remote": bool}
        validated_locations = []
        for loc in locations:
            if isinstance(loc, dict) and loc.get("location"):
                validated_locations.append({
                    "location": str(loc["location"]).strip()[:200],
                    "distance": loc.get("distance"),
                    "remote": bool(loc.get("remote", False)),
                })

        salary_min = search_prefs.get("salary_min")
        salary_max = search_prefs.get("salary_max")
        if salary_min is not None:
            salary_min = int(salary_min)
        if salary_max is not None:
            salary_max = int(salary_max)

        now = datetime.utcnow().isoformat()

        # Build SET expression dynamically — only touch provided fields
        set_parts = [
            "#uid = :uid",
            "daily_report = :dr",
            "weekly_report = :wr",
            "updated_at = :now",
        ]
        attr_values: Dict[str, Any] = {
            ":uid": f"USER#{user_sub}",
            ":dr": bool(daily_report),
            ":wr": bool(weekly_report),
            ":now": now,
        }
        attr_names: Dict[str, str] = {
            "#uid": "user_id",  # user_id is not reserved, but consistent alias style
        }

        # Always store the Cognito email — it's the authoritative address
        if cognito_email:
            set_parts.append("email = :email")
            attr_values[":email"] = cognito_email

        if role_queries:
            set_parts.append("role_queries = :rq")
            attr_values[":rq"] = role_queries

        if validated_locations:
            set_parts.append("search_locations = :sl")
            attr_values[":sl"] = validated_locations

        if salary_min is not None:
            set_parts.append("salary_min = :smin")
            attr_values[":smin"] = Decimal(str(salary_min))

        if salary_max is not None:
            set_parts.append("salary_max = :smax")
            attr_values[":smax"] = Decimal(str(salary_max))

        # created_at — set only if the attribute doesn't already exist
        set_parts.append("created_at = if_not_exists(created_at, :now)")

        update_expr = "SET " + ", ".join(set_parts)

        updated = dynamodb.update_item(
            table_name=users_table,
            key={"pk": f"USER#{user_sub}"},
            update_expression=update_expr,
            expression_attribute_values=attr_values,
            expression_attribute_names=attr_names,
        )
        updated = dynamo_deserialize(updated)

        return success_response({
            "user_id": updated.get("pk"),
            "email": cognito_email or updated.get("email"),
            "daily_report": updated.get("daily_report", False),
            "weekly_report": updated.get("weekly_report", False),
            "search_preferences": {
                "role_queries": role_queries,
                "locations": validated_locations,
                "salary_min": salary_min,
                "salary_max": salary_max,
            },
            "updated_at": now,
        })

    except json.JSONDecodeError:
        return error_response("Invalid JSON body", 400)
    except Exception as e:
        logger.error(f"Error updating user settings: {e}", exc_info=True)
        return error_response("Error updating settings", 500)


def get_resume_upload_url(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler for POST /user/resume/upload-url

    Returns a pre-signed S3 PUT URL the browser can use to upload a PDF
    directly to S3, bypassing the Lambda/API Gateway size limits.

    The S3 key is always `resumes/{user_sub}/resume.pdf` — one slot per user.
    The resume_parser Lambda fires automatically via S3 ObjectCreated notification
    once the upload completes.

    Additionally, immediately marks resume_status = "processing" in DynamoDB so
    the frontend can show an upload-in-progress state without waiting for S3
    to confirm the file landed.
    """
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    resumes_bucket = os.environ.get("RESUMES_BUCKET", "")
    users_table = os.environ.get("USERS_TABLE", "")

    if not resumes_bucket or not users_table:
        return error_response("Missing environment variables", 500)

    s3_key = f"resumes/{user_sub}/resume.pdf"

    try:
        # Generate a pre-signed PUT URL (5-minute expiry).
        # ContentType condition is enforced so only PDFs are accepted.
        upload_url = _s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": resumes_bucket,
                "Key": s3_key,
                "ContentType": "application/pdf",
            },
            ExpiresIn=300,
        )

        # Mark status as "processing" immediately so the UI can react
        now = datetime.utcnow().isoformat()
        dynamodb.update_item(
            users_table,
            key={"pk": f"USER#{user_sub}"},
            update_expression="SET resume_status = :s, resume_updated_at = :t",
            expression_attribute_values={":s": "processing", ":t": now},
        )

        logger.info(f"Generated resume upload URL for user {user_sub}")
        return success_response({
            "uploadUrl": upload_url,
            "s3Key": s3_key,
            "expiresIn": 300,
        })

    except Exception as exc:
        logger.error(f"Error generating upload URL for user {user_sub}: {exc}", exc_info=True)
        return error_response("Failed to generate upload URL", 500)


def delete_resume(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler for DELETE /user/resume

    Removes the resume PDF from S3 and clears all resume-related fields
    from the user's DynamoDB record. After this call, the user will no
    longer receive AI match scores until they upload a new resume.
    """
    user_sub = get_user_sub(event)
    if not user_sub:
        return unauthorized_response("Unauthorized")

    resumes_bucket = os.environ.get("RESUMES_BUCKET", "")
    users_table = os.environ.get("USERS_TABLE", "")

    if not resumes_bucket or not users_table:
        return error_response("Missing environment variables", 500)

    s3_key = f"resumes/{user_sub}/resume.pdf"

    try:
        # Best-effort S3 delete (no error if the object doesn't exist)
        try:
            _s3.delete_object(Bucket=resumes_bucket, Key=s3_key)
            logger.info(f"Deleted resume from S3: s3://{resumes_bucket}/{s3_key}")
        except Exception as s3_err:
            logger.warning(f"Non-blocking: S3 delete failed for {s3_key}: {s3_err}")

        # Clear all resume fields from DynamoDB
        now = datetime.utcnow().isoformat()
        dynamodb.update_item(
            users_table,
            key={"pk": f"USER#{user_sub}"},
            update_expression=(
                "REMOVE resume_text, resume_filename "
                "SET resume_status = :s, resume_updated_at = :t"
            ),
            expression_attribute_values={":s": "deleted", ":t": now},
        )

        logger.info(f"Cleared resume data for user {user_sub}")
        return success_response({"message": "Resume deleted successfully"})

    except Exception as exc:
        logger.error(f"Error deleting resume for user {user_sub}: {exc}", exc_info=True)
        return error_response("Failed to delete resume", 500)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler dispatcher — routes on resource path + HTTP method.

    Route table:
      GET    /user/settings           → get_settings
      PUT    /user/settings           → put_settings
      POST   /user/resume/upload-url  → get_resume_upload_url
      DELETE /user/resume             → delete_resume
    """
    http_method = event.get("httpMethod", "GET").upper()
    resource = event.get("resource", "")

    if resource == "/user/resume/upload-url" and http_method == "POST":
        return get_resume_upload_url(event, context)

    if resource == "/user/resume" and http_method == "DELETE":
        return delete_resume(event, context)

    # Default: /user/settings
    if http_method == "PUT":
        return put_settings(event, context)
    elif http_method == "GET":
        return get_settings(event, context)
    else:
        return error_response("Method not allowed", 405)
