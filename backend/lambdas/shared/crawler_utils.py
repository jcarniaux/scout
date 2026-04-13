"""
Utility functions for job crawlers.
"""
import json
import logging
import os
import re
from typing import List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cache secrets across invocations (Lambda container reuse)
_cached_secrets: Optional[dict] = None


def get_scraper_secrets() -> dict:
    """
    Retrieve scraper secrets from AWS Secrets Manager.
    Caches the result for the lifetime of the Lambda container.

    Returns:
        Dict of secret key/value pairs, or empty dict on failure.
    """
    global _cached_secrets
    if _cached_secrets is not None:
        return _cached_secrets

    secrets_arn = os.environ.get("SECRETS_ARN")
    if not secrets_arn:
        logger.warning("SECRETS_ARN not set — running without proxy/API keys")
        _cached_secrets = {}
        return _cached_secrets

    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secrets_arn)
        _cached_secrets = json.loads(resp["SecretString"])
        logger.info("Loaded scraper secrets from Secrets Manager")
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}", exc_info=True)
        _cached_secrets = {}

    return _cached_secrets


def _parse_proxy_strings() -> List[str]:
    """
    Read scraping_proxy from Secrets Manager and return a list of
    raw proxy strings (user:pass@host:port format).
    """
    secrets = get_scraper_secrets()
    proxy_value = secrets.get("scraping_proxy", "")

    if not proxy_value or proxy_value == "placeholder":
        logger.warning("No scraping proxy configured — requests will use Lambda IP")
        return []

    proxies = [p.strip() for p in proxy_value.split(",") if p.strip()]
    if proxies:
        logger.info(f"Loaded {len(proxies)} proxy/proxies from Secrets Manager")
    return proxies


def get_proxy_list() -> Optional[List[str]]:
    """
    Build a proxy list for use with JobSpy's 'proxies' parameter.

    JobSpy accepts proxies in 'user:pass@host:port' format and
    handles the HTTP/HTTPS wrapping internally.

    Used by the LinkedIn crawler (the only remaining JobSpy-based crawler).

    NOTE: Oxylabs Web Scraper API proxy endpoints are EXCLUDED because
    they perform TLS interception which is incompatible with JobSpy's
    tls_client library (causes x509 certificate verification failures).
    LinkedIn works fine without a proxy from Lambda IPs.

    Returns:
        List of proxy strings, or None if no proxies are configured.
    """
    proxies = _parse_proxy_strings()
    if not proxies:
        return None

    # Filter out Oxylabs proxies — they do TLS interception which
    # breaks tls_client inside JobSpy (x509 cert verification errors).
    compatible = [p for p in proxies if "oxylabs.io" not in p]

    if not compatible:
        logger.info("All configured proxies are Oxylabs — LinkedIn will run without proxy")
        return None

    return compatible


def extract_salary_min(job: any) -> Optional[int]:
    """
    Extract minimum salary from a JobSpy job object.

    JobSpy returns salary as:
    - min_amount: minimum salary
    - max_amount: maximum salary
    - Or as a string like "$180,000 - $220,000"

    Args:
        job: JobSpy job dataframe row

    Returns:
        Minimum salary as int, or None if not found
    """
    try:
        # Try min_amount field first
        if hasattr(job, "min_amount") and job.min_amount:
            val = job.min_amount
            if isinstance(val, str):
                # Remove currency symbols and commas
                val = re.sub(r"[^\d]", "", val)
                return int(val) if val else None
            return int(val)
    except (ValueError, AttributeError):
        pass

    # Try salary field (some sources have combined string)
    if hasattr(job, "salary") and job.salary:
        try:
            salary_str = str(job.salary)
            # Extract first number from string like "$180,000 - $220,000"
            matches = re.findall(r"\d+(?:,\d+)*", salary_str)
            if matches:
                return int(matches[0].replace(",", ""))
        except (ValueError, AttributeError):
            pass

    return None


def extract_salary_max(job: any) -> Optional[int]:
    """
    Extract maximum salary from a JobSpy job object.

    Args:
        job: JobSpy job dataframe row

    Returns:
        Maximum salary as int, or None if not found
    """
    try:
        # Try max_amount field first
        if hasattr(job, "max_amount") and job.max_amount:
            val = job.max_amount
            if isinstance(val, str):
                val = re.sub(r"[^\d]", "", val)
                return int(val) if val else None
            return int(val)
    except (ValueError, AttributeError):
        pass

    # Try salary field and extract second number
    if hasattr(job, "salary") and job.salary:
        try:
            salary_str = str(job.salary)
            matches = re.findall(r"\d+(?:,\d+)*", salary_str)
            if len(matches) > 1:
                return int(matches[1].replace(",", ""))
        except (ValueError, AttributeError):
            pass

    return None


def clean_field(value: any) -> str:
    """
    Sanitize a DataFrame cell to a clean string.

    JobSpy returns Python NaN (float) for missing fields.  ``str(NaN)``
    produces ``"nan"``; ``str(None)`` produces ``"None"``.  Both are
    useless sentinel strings that should be treated as empty.

    Returns:
        Stripped string, or "" if the value is missing/NaN/None.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    return s


def normalize_title(title: str) -> str:
    """Normalize job title to title case."""
    return title.strip().title() if title else ""


def normalize_company(company: str) -> str:
    """Normalize company name."""
    return company.strip() if company else ""


def normalize_location(location: str) -> str:
    """Normalize location string."""
    if not location:
        return ""
    # Clean up and title case
    cleaned = location.strip().title()
    return cleaned


def meets_location_requirement(location: Optional[str]) -> bool:
    """
    Check if a job's location is Atlanta/GA area or remote.

    Accepts:
    - Empty / None  — location parsing failed (common with Dice Phase 2);
                      the crawler already searched with Atlanta or remote
                      parameters, so these are assumed valid.
    - Atlanta, GA, Georgia area
    - Remote / work-from-home / hybrid (any US-based remote)
    - "United States" / national listings (inherently open to remote)

    Rejects:
    - Named cities/states that are clearly not Atlanta or US-remote
      (e.g. "Waterford, Ireland", "London, UK", "New York, NY")

    Args:
        location: Location string from crawler (may be empty)

    Returns:
        True if location is acceptable
    """
    if not location or location.strip().lower() in ("", "location unknown", "unknown"):
        return True  # No location data — assume valid (see note above)

    loc = location.lower()

    # Atlanta / Georgia
    if any(kw in loc for kw in ("atlanta", ", ga", "georgia", "ga,", "ga ")):
        return True

    # Remote / flexible work
    if any(kw in loc for kw in ("remote", "work from home", "wfh", "hybrid", "anywhere")):
        return True

    # "United States" only passes when it's a national/remote listing, NOT when
    # it's a city/state suffix on an in-person job (e.g. "Nebraska, United States").
    # Strategy: strip "united states" from the string and check what's left.
    # If the remainder is empty, "remote", or Atlanta/GA, it's valid.
    # If the remainder is a specific non-matching city/state, it's in-person elsewhere.
    for us_kw in ("united states", "u.s.", "nationwide"):
        if us_kw in loc:
            prefix = loc.replace(us_kw, "").strip(" ,")
            if not prefix:
                return True  # Just "United States" — national/remote listing
            if any(kw in prefix for kw in ("remote", "atlanta", ", ga", "georgia", "wfh", "anywhere")):
                return True  # "Remote, United States" or "Atlanta, GA, United States"
            # Has a specific non-matching location prefix → in-person elsewhere → reject

    return False


def meets_salary_requirement(salary_min: Optional[int], minimum_threshold: int = 0) -> bool:
    """
    Check if a salary meets minimum requirement.

    Args:
        salary_min: Minimum salary from job posting
        minimum_threshold: Required minimum salary

    Returns:
        True if salary meets or exceeds threshold (or if no salary info)
    """
    if salary_min is None:
        # No salary info, assume it meets requirement
        return True
    return salary_min >= minimum_threshold
