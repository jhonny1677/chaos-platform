"""
SlackClient — Posts Block Kit messages to Slack via Incoming Webhook.

Webhook URL is kept in SSM Parameter Store (SecureString) and resolved
once per Lambda container cold start. It is never logged or returned in
responses to prevent accidental exposure.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def post(
        self,
        channel: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> bool:
        """
        Post a message to Slack.

        Returns True on success, False on non-fatal Slack errors.
        Raises urllib.error.HTTPError on 5xx responses (Lambda will retry).
        """
        payload: dict[str, Any] = {
            "channel": channel,
            "text":    text,
        }
        if blocks:
            payload["blocks"] = blocks

        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_text = resp.read().decode("utf-8")
                if response_text == "ok":
                    logger.info("Slack message posted successfully to %s", channel)
                    return True
                # Slack returns "ok" for success and an error string for failures
                logger.warning("Slack returned non-ok response: %s", response_text)
                return False

        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                # Slack server error — raise so Lambda retries
                logger.error("Slack 5xx error: %s %s", exc.code, exc.reason)
                raise
            # 4xx = bad request (wrong webhook, invalid blocks) — log and move on
            logger.error("Slack 4xx error: %s %s body=%s", exc.code, exc.reason,
                         exc.read().decode("utf-8", errors="replace"))
            return False

        except urllib.error.URLError as exc:
            logger.error("Network error posting to Slack: %s", exc.reason)
            return False
