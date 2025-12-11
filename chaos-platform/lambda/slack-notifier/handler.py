"""
Lambda: slack-notifier
Triggered by: SNS topic chaos-notifications

Accepts the following event types (set as SNS message attribute "eventType"):
  experiment.started      — chaos experiment just kicked off
  experiment.completed    — experiment finished, hypothesis evaluated
  experiment.failed       — experiment errored out mid-run
  load-test.completed     — load test finished
  alert.fired             — Alertmanager webhook forwarded to SNS
  report.generated        — PDF report is ready (from report-generator lambda)

Each event type is routed to its own formatter, then posted to Slack.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from message_formatter import MessageFormatter
from slack_client import SlackClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WEBHOOK_URL        = os.environ.get("SLACK_WEBHOOK_URL", "")
SSM_WEBHOOK_PARAM  = os.environ.get("SLACK_WEBHOOK_SSM_PARAM", "/chaos-platform/slack/webhook-url")
DEFAULT_CHANNEL    = os.environ.get("SLACK_DEFAULT_CHANNEL", "#chaos-platform-alerts")

# Per-event-type channel overrides
CHANNEL_MAP = {
    "experiment.started":    os.environ.get("CHANNEL_EXPERIMENTS", "#chaos-experiments"),
    "experiment.completed":  os.environ.get("CHANNEL_EXPERIMENTS", "#chaos-experiments"),
    "experiment.failed":     os.environ.get("CHANNEL_EXPERIMENTS", "#chaos-experiments"),
    "load-test.completed":   os.environ.get("CHANNEL_LOAD_TESTS",  "#load-tests"),
    "alert.fired":           os.environ.get("CHANNEL_ALERTS",      "#chaos-platform-alerts"),
    "report.generated":      os.environ.get("CHANNEL_REPORTS",     "#chaos-reports"),
}


def _log(level: str, msg: str, **kwargs: Any) -> None:
    logger.log(
        getattr(logging, level.upper()),
        json.dumps({"message": msg, **kwargs}),
    )


def _resolve_webhook() -> str:
    """Return webhook URL from env var or SSM Parameter Store (preferred in prod)."""
    if WEBHOOK_URL:
        return WEBHOOK_URL

    # Lazy import — avoids cold-start penalty when env var is set
    import boto3
    ssm = boto3.client("ssm")
    resp = ssm.get_parameter(Name=SSM_WEBHOOK_PARAM, WithDecryption=True)
    url  = resp["Parameter"]["Value"]
    _log("info", "Loaded Slack webhook URL from SSM", param=SSM_WEBHOOK_PARAM)
    return url


def lambda_handler(event: dict, context: Any) -> dict:
    _log("info", "slack-notifier invoked", record_count=len(event.get("Records", [])))

    results = []
    formatter = MessageFormatter()

    for record in event.get("Records", []):
        try:
            sns_record  = record["Sns"]
            raw_message = sns_record["Message"]
            attrs       = sns_record.get("MessageAttributes", {})

            # Event type from SNS message attribute (preferred) or message body
            event_type = (
                attrs.get("eventType", {}).get("Value")
                or json.loads(raw_message).get("eventType", "unknown")
            )
            message_body = json.loads(raw_message)

            _log("info", "processing SNS record", event_type=event_type)

            # Route to formatter
            blocks = _format(formatter, event_type, message_body)
            if blocks is None:
                _log("warning", "no formatter for event type", event_type=event_type)
                results.append({"status": "skipped", "eventType": event_type})
                continue

            channel = CHANNEL_MAP.get(event_type, DEFAULT_CHANNEL)
            webhook = _resolve_webhook()
            client  = SlackClient(webhook)

            success = client.post(
                channel=channel,
                text=f"Chaos Platform: {event_type}",  # fallback plain text
                blocks=blocks,
            )

            _log("info", "Slack post result", success=success, event_type=event_type,
                 channel=channel)
            results.append({"status": "ok" if success else "failed", "eventType": event_type})

        except Exception as exc:  # noqa: BLE001
            _log("error", "failed to process record", error=str(exc),
                 exc_type=type(exc).__name__)
            results.append({"status": "error", "error": str(exc)})

    all_ok = all(r["status"] == "ok" for r in results)
    return {
        "statusCode": 200 if all_ok else 207,
        "body": json.dumps({"results": results}),
    }


def _format(formatter: MessageFormatter, event_type: str, body: dict) -> list | None:
    dispatch = {
        "experiment.started":    formatter.format_experiment_started,
        "experiment.completed":  formatter.format_experiment_completed,
        "experiment.failed":     formatter.format_experiment_failed,
        "load-test.completed":   formatter.format_load_test_completed,
        "alert.fired":           formatter.format_alert_fired,
        "report.generated":      formatter.format_report_generated,
    }
    fn = dispatch.get(event_type)
    return fn(body) if fn else None
