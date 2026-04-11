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

    When an Oxylabs (or similar TLS-intercepting) proxy is detected,
    this also patches tls_client so JobSpy's internal HTTPS calls
    accept the proxy's re-signed certificate.

    Returns:
        List of proxy strings, or None if no proxies are configured.
    """
    proxies = _parse_proxy_strings()
    if not proxies:
        return None

    # If any proxy does TLS interception, apply patches
    if any("oxylabs.io" in p for p in proxies):
        _patch_tls_client_for_proxy()
        _patch_jobspy_timeout_for_proxy()

    return proxies


# Guards so monkey-patches only run once per Lambda container
_tls_client_patched = False
_jobspy_timeout_patched = False

# Proxy services add latency (TLS interception, anti-bot, rendering).
# JobSpy's default 10s is too aggressive.
PROXY_TIMEOUT_SECONDS = 45


def _patch_tls_client_for_proxy() -> None:
    """
    Monkey-patch tls_client.Session to skip TLS certificate verification.

    JobSpy uses tls_client internally (for Glassdoor, etc.). The Oxylabs
    Web Scraper API proxy endpoint terminates TLS and re-signs responses
    with its own CA, causing 'x509: certificate signed by unknown authority'
    errors. This patch injects insecure_skip_verify=True into every
    tls_client.Session created by JobSpy.

    Only runs once — safe to call repeatedly.
    """
    global _tls_client_patched
    if _tls_client_patched:
        return

    try:
        import tls_client

        _original_init = tls_client.Session.__init__

        def _patched_init(self, *args, **kwargs):
            kwargs["insecure_skip_verify"] = True
            _original_init(self, *args, **kwargs)

        tls_client.Session.__init__ = _patched_init
        _tls_client_patched = True
        logger.info("Patched tls_client.Session with insecure_skip_verify=True for proxy")
    except ImportError:
        logger.debug("tls_client not installed — no patch needed")
    except Exception as e:
        logger.warning(f"Failed to patch tls_client for proxy: {e}")


def _patch_jobspy_timeout_for_proxy() -> None:
    """
    Increase JobSpy's internal HTTP timeout for proxied requests.

    JobSpy defaults to ~10 s read timeout, which is too short when
    requests route through a scraping proxy (Oxylabs adds latency for
    TLS interception, anti-bot handling, and optional JS rendering).

    This finds JobSpy's custom requests.Session subclass in jobspy.util
    and patches its request() method to enforce PROXY_TIMEOUT_SECONDS.

    Only runs once — safe to call repeatedly.
    """
    global _jobspy_timeout_patched
    if _jobspy_timeout_patched:
        return

    try:
        import importlib
        import requests as _req

        jobspy_util = importlib.import_module("jobspy.util")

        # JobSpy wraps requests.Session in a subclass inside jobspy.util.
        # Find it and patch its request() method.
        for attr_name in dir(jobspy_util):
            cls = getattr(jobspy_util, attr_name, None)
            if (
                isinstance(cls, type)
                and issubclass(cls, _req.Session)
                and cls is not _req.Session
                and hasattr(cls, "request")
            ):
                _orig_request = cls.request

                def _patched_request(
                    self,
                    method,
                    url,
                    *args,
                    _orig=_orig_request,
                    _timeout=PROXY_TIMEOUT_SECONDS,
                    **kwargs,
                ):
                    # Set timeout if missing, or raise it if below minimum
                    current = kwargs.get("timeout")
                    if current is None:
                        kwargs["timeout"] = _timeout
                    elif isinstance(current, (int, float)) and current < _timeout:
                        kwargs["timeout"] = _timeout
                    return _orig(self, method, url, *args, **kwargs)

                cls.request = _patched_request
                _jobspy_timeout_patched = True
                logger.info(
                    f"Patched {cls.__name__}.request timeout to "
                    f"{PROXY_TIMEOUT_SECONDS}s for proxy latency"
                )
                return

        logger.debug("No custom session subclass found in jobspy.util — skipping timeout patch")
    except ImportError:
        logger.debug("jobspy not installed — no timeout patch needed")
    except Exception as e:
        logger.warning(f"Failed to patch JobSpy timeout for proxy: {e}")


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
