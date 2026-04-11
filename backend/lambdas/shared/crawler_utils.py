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

    Returns:
        List of proxy strings, or None if no proxies are configured.
    """
    proxies = _parse_proxy_strings()
    return proxies if proxies else None


def get_requests_proxy_dict() -> tuple[Optional[dict], bool]:
    """
    Build a requests-compatible proxy dict for direct HTTP calls
    (e.g., the Dice crawler which uses requests.Session directly).

    Handles Oxylabs Web Scraper API proxy endpoint which requires:
      - HTTPS connection to the proxy (realtime.oxylabs.io:60000)
      - SSL verification disabled (proxy does TLS termination)

    Returns:
        Tuple of (proxy_dict, skip_ssl_verify):
          - proxy_dict: {"http": "...", "https": "..."} or None
          - skip_ssl_verify: True if the proxy requires verify=False
    """
    proxies = _parse_proxy_strings()
    if not proxies:
        return None, False

    import random
    proxy = random.choice(proxies)

    # Detect Oxylabs Web Scraper API proxy endpoint
    is_oxylabs = "oxylabs.io" in proxy

    if proxy.startswith("socks"):
        return {"http": proxy, "https": proxy}, False

    if is_oxylabs:
        # Oxylabs proxy endpoint requires HTTPS to the proxy itself.
        # The proxy handles TLS termination, so we must skip SSL
        # verification on the client-to-proxy connection.
        proxy_url = f"https://{proxy}" if not proxy.startswith("http") else proxy
        return {"http": proxy_url, "https": proxy_url}, True

    # Standard HTTP proxy
    proxy_url = f"http://{proxy}" if not proxy.startswith("http") else proxy
    return {"http": proxy_url, "https": proxy_url}, False


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


def meets_salary_requirement(salary_min: Optional[int], minimum_threshold: int = 180000) -> bool:
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
