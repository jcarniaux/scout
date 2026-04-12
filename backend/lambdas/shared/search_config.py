"""
Load search preferences from DynamoDB users table.

Crawlers call `load_search_config()` at startup to get the merged
search preferences across all users.  Falls back to the hardcoded
defaults in shared.models when no preferences are stored.

Design decision: scan all users, merge their preferences (union of
roles/locations, lowest salary minimum).  At Scout's scale (handful
of users) this is a single lightweight DDB scan per crawler invocation.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from shared.db import DynamoDBHelper
from shared.models import (
    ROLE_QUERIES as DEFAULT_ROLES,
    LOCATIONS as DEFAULT_LOCATIONS,
    SALARY_MINIMUM as DEFAULT_SALARY_MIN,
    dynamo_deserialize,
)

logger = logging.getLogger(__name__)

_dynamodb = DynamoDBHelper()


def load_search_config() -> Dict[str, Any]:
    """
    Read all users' search preferences and return a merged config.

    Returns:
        {
            "role_queries": ["Security Engineer", ...],
            "locations": [{"location": "Atlanta, GA", "distance": 25, "remote": False}, ...],
            "salary_minimum": 180000,
        }
    """
    users_table = os.environ.get("USERS_TABLE")
    if not users_table:
        logger.warning("USERS_TABLE not set — using default search config")
        return _defaults()

    try:
        items, _ = _dynamodb.scan(users_table)
    except Exception as e:
        logger.warning(f"Failed to scan users table: {e} — using defaults")
        return _defaults()

    if not items:
        logger.info("No users found — using default search config")
        return _defaults()

    all_roles: set = set()
    all_locations: List[Dict[str, Any]] = []
    seen_locations: set = set()
    salary_minimum: Optional[int] = None

    for raw_item in items:
        item = dynamo_deserialize(raw_item)

        # Merge role queries (union)
        roles = item.get("role_queries")
        if isinstance(roles, (list, set)):
            for r in roles:
                if isinstance(r, str) and r.strip():
                    all_roles.add(r.strip())

        # Merge locations (deduplicate by (location, remote) tuple)
        locs = item.get("search_locations")
        if isinstance(locs, list):
            for loc in locs:
                if isinstance(loc, dict) and loc.get("location"):
                    key = (loc["location"].lower(), bool(loc.get("remote", False)))
                    if key not in seen_locations:
                        seen_locations.add(key)
                        all_locations.append({
                            "location": str(loc["location"]),
                            "distance": loc.get("distance"),
                            "remote": bool(loc.get("remote", False)),
                        })

        # Salary minimum — use the lowest across all users
        user_sal = item.get("salary_min")
        if user_sal is not None:
            try:
                val = int(user_sal)
                if salary_minimum is None or val < salary_minimum:
                    salary_minimum = val
            except (ValueError, TypeError):
                pass

    config = {
        "role_queries": list(all_roles) if all_roles else list(DEFAULT_ROLES),
        "locations": all_locations if all_locations else list(DEFAULT_LOCATIONS),
        "salary_minimum": salary_minimum if salary_minimum is not None else DEFAULT_SALARY_MIN,
    }

    logger.info(
        f"Search config loaded: {len(config['role_queries'])} roles, "
        f"{len(config['locations'])} locations, "
        f"salary_min=${config['salary_minimum']:,}"
    )
    return config


def _defaults() -> Dict[str, Any]:
    """Return the hardcoded defaults from models.py."""
    return {
        "role_queries": list(DEFAULT_ROLES),
        "locations": list(DEFAULT_LOCATIONS),
        "salary_minimum": DEFAULT_SALARY_MIN,
    }
