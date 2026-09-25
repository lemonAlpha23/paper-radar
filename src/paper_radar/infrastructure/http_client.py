import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from paper_radar.config.settings import Settings
from paper_radar.core.exceptions import RadarError

logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
            transport=transport,
        )
        self.retry_count = 0
        self._last_request = 0.0

    def close(self) -> None:
        self.client.close()

    def get_text(self, url: str) -> str:
        for attempt in range(self.settings.max_retries + 1):
            time.sleep(
                max(0, self.settings.request_interval - (time.monotonic() - self._last_request))
            )
            self._last_request = time.monotonic()
            response = None
            try:
                response = self.client.get(url)
            except httpx.TransportError:
                if attempt == self.settings.max_retries:
                    raise RadarError("Source request failed after transport retries") from None
            else:
                if response.is_success:
                    return response.text
                if response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise RadarError(f"Source returned HTTP {response.status_code}")
                if attempt == self.settings.max_retries:
                    raise RadarError(f"Source returned HTTP {response.status_code} after retries")
            delay = float(2**attempt)
            if response is not None and (retry_after := response.headers.get("Retry-After")):
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(
                            delay,
                            (
                                parsedate_to_datetime(retry_after) - datetime.now(UTC)
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError, OverflowError):
                        logger.warning("Invalid Retry-After header; using exponential backoff")
            if delay > 300:
                raise RadarError("Server requested a retry delay over 300 seconds; retry later")
            self.retry_count += 1
            logger.warning("status=retry retry_count=%s delay=%.1f", self.retry_count, delay)
            time.sleep(delay)
        raise AssertionError("Unreachable retry state")

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        # A timeout may happen after delivery. Retrying a POST could send duplicate messages.
        try:
            if files is None:
                response = self.client.post(url, json=payload)
            else:
                response = self.client.post(url, data=payload, files=files)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            raise RadarError("Notification request failed; delivery may be unknown") from None
        if not isinstance(body, dict):
            raise RadarError("Notification response must be a JSON object")
        return body
