"""
API Gateway Lambda proxy response helpers for Scout backend.
"""
import json
import logging
import os
from typing import Any, Dict


def get_cors_headers() -> Dict[str, str]:
    """
    Get CORS headers for API Gateway responses.

    SITE_URL must be set in each Lambda's environment variables.
    Falls back to rejecting cross-origin requests (empty origin)
    rather than allowing all origins with '*'.

    Returns:
        Dict with CORS headers
    """
    site_url = os.environ.get("SITE_URL", "")
    if not site_url:
        logging.getLogger().warning(
            "SITE_URL environment variable not set — CORS origin will be empty. "
            "Set SITE_URL to the frontend URL (e.g. https://scout.carniaux.io)."
        )
    return {
        "Access-Control-Allow-Origin": site_url,
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
        "Content-Type": "application/json",
    }


def cors_response(status_code: int, body: Any) -> Dict[str, Any]:
    """
    Build a standard API Gateway Lambda proxy response with CORS headers.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON-serialized)

    Returns:
        Lambda proxy response dict
    """
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps(body, default=str),
    }


def success_response(body: Any = None, status_code: int = 200) -> Dict[str, Any]:
    """
    Build a successful response.

    Args:
        body: Response body
        status_code: HTTP status code (default 200)

    Returns:
        Lambda proxy response dict
    """
    if body is None:
        body = {"success": True}
    return cors_response(status_code, body)


def error_response(message: str, status_code: int = 400) -> Dict[str, Any]:
    """
    Build an error response.

    Args:
        message: Error message
        status_code: HTTP status code (default 400)

    Returns:
        Lambda proxy response dict
    """
    return cors_response(status_code, {"error": message})


def not_found_response(message: str = "Not found") -> Dict[str, Any]:
    """Build a 404 response."""
    return error_response(message, 404)


def unauthorized_response(message: str = "Unauthorized") -> Dict[str, Any]:
    """Build a 401 response."""
    return error_response(message, 401)


def forbidden_response(message: str = "Forbidden") -> Dict[str, Any]:
    """Build a 403 response."""
    return error_response(message, 403)
