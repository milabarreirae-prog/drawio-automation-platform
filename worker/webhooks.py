"""
Webhook Notification System.

Sends task completion/failure notifications to external webhook URLs
using httpx with retry logic and timeout controls.

Notifications are sent for:
- COMPLETED: Diagram rendered and uploaded to S3 successfully
- DEGRADED: Rendered with fallback (placeholders, missing stencils)
- FAILED: Rendering failed (classified error)
- REJECTED: Blocked by compliance policy or license
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from api.config import Settings, get_settings
from worker.models import FallbackReport

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """
    Async webhook notifier with retry logic.

    Sends JSON payloads to webhook URLs for task status updates.
    Uses httpx with configurable timeout and retry settings.

    Usage:
        notifier = WebhookNotifier()
        await notifier.notify("https://hooks.example.com/callback", report)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an httpx async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.webhook_timeout),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "drawio-automation-platform/0.1.0",
                    "X-Drawio-Automation": "true",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def notify(
        self,
        webhook_url: str,
        report: FallbackReport,
    ) -> bool:
        """
        Send a webhook notification for a task.

        Args:
            webhook_url: Target URL to POST the notification to.
            report: FallbackReport with task status, results, and errors.

        Returns:
            True if notification was delivered successfully.

        Note:
            Webhook delivery failures are logged but do NOT fail the task.
            The task result is always available via the status API endpoint.
        """
        if not webhook_url:
            logger.debug("No webhook URL configured — skipping notification for task %s", report.task_id)
            return False

        payload = report.to_webhook_payload()
        max_retries = self.settings.webhook_max_retries

        client = await self._get_client()

        for attempt in range(max_retries + 1):
            try:
                logger.debug("Sending webhook for task %s (attempt %d/%d) to %s", report.task_id, attempt + 1, max_retries + 1, webhook_url[:80])

                response = await client.post(webhook_url, json=payload)

                if 200 <= response.status_code < 300:
                    logger.info("Webhook delivered for task %s (status=%s, status_code=%d)", report.task_id, report.status.value, response.status_code)
                    return True

                # Non-2xx response — log and retry
                logger.warning(
                    "Webhook for task %s returned status %d (attempt %d/%d): %s",
                    report.task_id,
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    response.text[:500],
                )

                if attempt < max_retries:
                    # Only retry on server errors (5xx) or specific client errors (429)
                    if response.status_code >= 500 or response.status_code == 429:
                        await self._wait_before_retry(attempt)
                        continue
                    else:
                        logger.warning("Non-retryable webhook status %d for task %s — giving up", response.status_code, report.task_id)
                        break

            except httpx.TimeoutException:
                logger.warning("Webhook timeout for task %s (attempt %d/%d)", report.task_id, attempt + 1, max_retries + 1)
                if attempt < max_retries:
                    await self._wait_before_retry(attempt)

            except httpx.RequestError as e:
                logger.warning("Webhook request error for task %s (attempt %d/%d): %s", report.task_id, attempt + 1, max_retries + 1, e)
                if attempt < max_retries:
                    await self._wait_before_retry(attempt)

            except Exception as e:
                logger.error("Unexpected webhook error for task %s: %s", report.task_id, e)
                if attempt < max_retries:
                    await self._wait_before_retry(attempt)

        logger.error(
            "Failed to deliver webhook for task %s after %d attempts — task result is still available via API",
            report.task_id,
            max_retries + 1,
        )
        return False

    async def _wait_before_retry(self, attempt: int) -> None:
        """Wait before retrying with exponential backoff."""
        import asyncio

        delay = 2 ** (attempt + 1)  # 2s, 4s
        logger.debug("Waiting %ds before webhook retry", delay)
        await asyncio.sleep(delay)

    async def notify_batch(
        self,
        webhook_url: str,
        reports: list[FallbackReport],
    ) -> dict[str, bool]:
        """
        Send notifications for multiple tasks to the same webhook URL.

        Args:
            webhook_url: Target URL.
            reports: List of task reports to send.

        Returns:
            Dict mapping task_id to delivery success.
        """
        results: dict[str, bool] = {}
        for report in reports:
            results[report.task_id] = await self.notify(webhook_url, report)
        return results