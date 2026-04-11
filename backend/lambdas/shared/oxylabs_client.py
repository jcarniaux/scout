"""
Oxylabs Web Scraper API Realtime client.

Uses the Realtime integration method (synchronous POST) to fetch
fully rendered web pages. Oxylabs handles anti-bot, CAPTCHAs, IP
rotation, and JavaScript rendering on their infrastructure.

Credentials are read from AWS Secrets Manager (SECRETS_ARN env var).
Expects either:
  - oxylabs_username + oxylabs_password keys, OR
  - scraping_proxy in "user:pass@host:port" format (legacy, parsed)
"""
import logging
from typing import Optional

import requests

from shared.crawler_utils import get_scraper_secrets

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REALTIME_URL = "https://realtime.oxylabs.io/v1/queries"
DEFAULT_TIMEOUT = 90  # Oxylabs may take time to render + solve CAPTCHAs


class OxylabsClient:
    """Synchronous client for the Oxylabs Realtime API."""

    def __init__(self) -> None:
        secrets = get_scraper_secrets()
        self.username, self.password = self._extract_credentials(secrets)

        if not self.username or not self.password:
            raise RuntimeError(
                "Oxylabs credentials not found in Secrets Manager. "
                "Set 'oxylabs_username'+'oxylabs_password' or 'scraping_proxy'."
            )

        logger.info("OxylabsClient initialized")

    @staticmethod
    def _extract_credentials(secrets: dict) -> tuple[Optional[str], Optional[str]]:
        """
        Extract Oxylabs username and password from secrets.

        Supports two formats:
          1. Explicit keys: oxylabs_username, oxylabs_password
          2. Legacy proxy string: scraping_proxy = "user:pass@host:port"
        """
        # Prefer explicit keys
        username = secrets.get("oxylabs_username")
        password = secrets.get("oxylabs_password")

        if username and password:
            return username, password

        # Fall back to parsing the proxy string
        proxy = secrets.get("scraping_proxy", "")
        if proxy and "@" in proxy and proxy != "placeholder":
            creds_part = proxy.split("@")[0]
            if ":" in creds_part:
                parts = creds_part.split(":", 1)
                return parts[0], parts[1]

        return None, None

    def fetch_page(
        self,
        url: str,
        render: bool = True,
        geo_location: str = "United States",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Optional[str]:
        """
        Fetch a fully rendered web page via Oxylabs Realtime API.

        Args:
            url: Target URL to scrape
            render: Whether to render JavaScript (True for SPAs)
            geo_location: Country for geo-targeting the request
            timeout: Request timeout in seconds

        Returns:
            HTML string of the rendered page, or None on failure.
        """
        payload = {
            "source": "universal",
            "url": url,
            "geo_location": geo_location,
        }

        if render:
            payload["render"] = "html"

        try:
            response = requests.post(
                REALTIME_URL,
                auth=(self.username, self.password),
                json=payload,
                timeout=timeout,
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    content = results[0].get("content", "")
                    status_code = results[0].get("status_code")
                    if status_code and status_code != 200:
                        logger.warning(
                            f"Oxylabs returned target status {status_code} for {url}"
                        )
                    return content
                else:
                    logger.warning(f"Oxylabs returned empty results for {url}")
                    return None

            elif response.status_code == 401:
                logger.error("Oxylabs authentication failed — check credentials")
                return None

            elif response.status_code == 422:
                logger.error(f"Oxylabs rejected request for {url}: {response.text}")
                return None

            else:
                logger.error(
                    f"Oxylabs returned {response.status_code} for {url}: "
                    f"{response.text[:200]}"
                )
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Oxylabs request timed out after {timeout}s for {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Oxylabs request failed for {url}: {e}")
            return None
