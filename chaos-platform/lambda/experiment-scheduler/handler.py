"""
Lambda: experiment-scheduler
Triggered by: EventBridge cron rule (default: 02:00 UTC Monday–Friday)

Reads scheduled experiments from DynamoDB, filters to those due to run,
and calls the Chaos Engine REST API to trigger each one. If the Chaos Engine
is unavailable, retries up to 3 times with exponential backoff, then sends
a Slack alert via SNS and marks the experiment as skipped.

DynamoDB schema for scheduled experiments:
  experimentId:      str (partition key)
  type:              str (pod-kill | network-delay | cpu-stress | memory-stress)
  scheduleExpression: str (cron-style: "Mon,Wed,Fri" | "daily" | "weekly")
  targetNamespace:   str
  targetLabel:       str
  durationSeconds:   int
  blastRadius:       float  (0.0–1.0, e.g. 0.5 for 50%)
  enabled:           bool
  lastRunAt:         int   (Unix timestamp of last successful trigger)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from scheduler_client import SchedulerClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, msg: str, **kwargs: Any) -> None:
    logger.log(
        getattr(logging, level.upper()),
        json.dumps({"message": msg, **kwargs}),
    )


TABLE_NAME        = os.environ["DYNAMODB_TABLE"]
CHAOS_ENGINE_URL  = os.environ["CHAOS_ENGINE_URL"]
SNS_TOPIC_ARN     = os.environ.get("SLACK_SNS_TOPIC_ARN", "")
MAX_RETRIES       = 3

dynamodb  = boto3.resource("dynamodb")
sns_client = boto3.client("sns")
table     = dynamodb.Table(TABLE_NAME)


def lambda_handler(event: dict, context: Any) -> dict:
    now_utc = datetime.now(tz=timezone.utc)
    _log("info", "experiment-scheduler invoked", utc_time=now_utc.isoformat())

    scheduled = _fetch_scheduled_experiments()
    due        = [e for e in scheduled if _is_due(e, now_utc)]
    _log("info", "experiment check", total=len(scheduled), due=len(due))

    results = []
    for experiment in due:
        result = _trigger_experiment(experiment, now_utc)
        results.append(result)
        if result["status"] == "skipped":
            _alert_slack(experiment, result.get("error", "Unknown"))

    summary = {
        "triggered": sum(1 for r in results if r["status"] == "triggered"),
        "skipped":   sum(1 for r in results if r["status"] == "skipped"),
        "total_due": len(due),
    }
    _log("info", "scheduler run complete", **summary)

    return {"statusCode": 200, "body": json.dumps({"summary": summary, "results": results})}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_scheduled_experiments() -> list[dict]:
    """Scan DynamoDB for all enabled scheduled experiments."""
    response = table.scan(
        FilterExpression="enabled = :true",
        ExpressionAttributeValues={":true": True},
    )
    return response.get("Items", [])


def _is_due(experiment: dict, now: datetime) -> bool:
    """
    Determine if an experiment should run now based on its scheduleExpression
    and the last time it was run. Prevents double-triggering within 23 hours.
    """
    expr       = experiment.get("scheduleExpression", "daily")
    last_run   = experiment.get("lastRunAt", 0)

    # Must not run again within 23 hours regardless of schedule
    if time.time() - int(last_run) < 23 * 3600:
        return False

    weekday = now.strftime("%A")[:3]  # Mon, Tue, Wed, Thu, Fri, Sat, Sun

    if expr == "daily":
        return True
    if expr == "weekly" and weekday == "Mon":
        return True
    if weekday in expr:   # e.g. scheduleExpression: "Mon,Wed,Fri"
        return True
    return False


def _trigger_experiment(experiment: dict, now: datetime) -> dict:
    """
    POST to the Chaos Engine API to trigger the experiment.
    Retries up to MAX_RETRIES times with exponential backoff.
    """
    exp_id = experiment.get("experimentId", "unknown")
    _log("info", "triggering experiment", experiment_id=exp_id)

    client = SchedulerClient(CHAOS_ENGINE_URL)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.trigger(experiment)
            # Update lastRunAt so we don't double-trigger
            _update_last_run(exp_id, now)
            _log("info", "experiment triggered", experiment_id=exp_id,
                 attempt=attempt, response=response)
            return {"status": "triggered", "experimentId": exp_id, "attempt": attempt}

        except Exception as exc:  # noqa: BLE001
            _log("warning", "trigger attempt failed", experiment_id=exp_id,
                 attempt=attempt, error=str(exc))
            if attempt < MAX_RETRIES:
                sleep_time = 2 ** attempt   # 2s, 4s, 8s
                _log("info", "retrying", experiment_id=exp_id, sleep_seconds=sleep_time)
                time.sleep(sleep_time)
            else:
                _log("error", "all retries exhausted", experiment_id=exp_id,
                     error=str(exc))
                return {"status": "skipped", "experimentId": exp_id, "error": str(exc)}

    return {"status": "skipped", "experimentId": exp_id, "error": "max retries exceeded"}


def _update_last_run(exp_id: str, now: datetime) -> None:
    try:
        table.update_item(
            Key={"experimentId": exp_id},
            UpdateExpression="SET lastRunAt = :ts",
            ExpressionAttributeValues={":ts": int(now.timestamp())},
        )
    except ClientError as exc:
        _log("warning", "failed to update lastRunAt", experiment_id=exp_id,
             error=str(exc))


def _alert_slack(experiment: dict, error: str) -> None:
    if not SNS_TOPIC_ARN:
        return
    exp_id = experiment.get("experimentId", "unknown")
    message = {
        "eventType":  "alert.fired",
        "alertName":  "ExperimentSchedulerFailed",
        "severity":   "error",
        "description": (
            f"Failed to trigger scheduled experiment `{exp_id}` after {MAX_RETRIES} attempts. "
            f"The Chaos Engine API may be unreachable. Error: {error}"
        ),
    }
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(message),
            MessageAttributes={
                "eventType": {"DataType": "String", "StringValue": "alert.fired"}
            },
        )
        _log("info", "slack alert sent", experiment_id=exp_id)
    except ClientError as exc:
        _log("error", "failed to publish slack alert", error=str(exc))
