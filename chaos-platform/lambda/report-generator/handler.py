"""
Lambda: report-generator
Triggered by:
  - S3 ObjectCreated event when an experiment result JSON lands in the results bucket
  - SNS message from the chaos engine on experiment completion
  - EventBridge weekly schedule (Monday 08:00 UTC) for weekly summary reports

Flow:
  1. Parse trigger to get experiment / load-test ID
  2. Read full result from DynamoDB
  3. Build HTML report (report_builder)
  4. Convert HTML → PDF (pdf_generator)
  5. Upload PDF to S3 reports bucket (s3_uploader)
  6. Publish Slack notification with presigned download URL
  7. Return report metadata
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from report_builder import ReportBuilder
from pdf_generator import PDFGenerator
from s3_uploader import S3Uploader

# ── Structured logging ────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, msg: str, **kwargs: Any) -> None:
    logger.log(
        getattr(logging, level.upper()),
        json.dumps({"message": msg, **kwargs}),
    )


# ── AWS clients (initialised once per container, reused across warm invocations)
dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
SNS_TOPIC_ARN = os.environ.get("SLACK_SNS_TOPIC_ARN", "")

table = dynamodb.Table(TABLE_NAME)


# ── Entry point ───────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    _log("info", "report-generator invoked", event_keys=list(event.keys()))
    start = time.time()

    try:
        experiment_id = _parse_experiment_id(event)
        _log("info", "resolved experiment ID", experiment_id=experiment_id)

        result_data = _fetch_result(experiment_id)
        _log("info", "fetched DynamoDB record", experiment_id=experiment_id,
             record_type=result_data.get("type", "unknown"))

        html = ReportBuilder(result_data).build()
        pdf_bytes = PDFGenerator().to_pdf(html)

        uploader = S3Uploader(REPORTS_BUCKET)
        presigned_url = uploader.upload(
            key=f"reports/{experiment_id}.pdf",
            pdf_bytes=pdf_bytes,
        )
        _log("info", "PDF uploaded", presigned_url=presigned_url)

        _notify_slack(result_data, presigned_url)

        elapsed_ms = int((time.time() - start) * 1000)
        _log("info", "report-generator complete", elapsed_ms=elapsed_ms,
             experiment_id=experiment_id)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "experimentId": experiment_id,
                "reportUrl": presigned_url,
                "elapsedMs": elapsed_ms,
            }),
        }

    except (KeyError, ValueError) as exc:
        _log("error", "bad event shape", error=str(exc))
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    except ClientError as exc:
        _log("error", "AWS client error", error=str(exc),
             code=exc.response["Error"]["Code"])
        raise   # re-raise so Lambda marks as failed and EventBridge can retry
    except Exception as exc:
        _log("error", "unexpected error", error=str(exc), exc_type=type(exc).__name__)
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_experiment_id(event: dict) -> str:
    """Support three trigger shapes: S3, SNS, and EventBridge direct invocation."""

    # SNS trigger wraps the payload in Records[0].Sns.Message
    if "Records" in event:
        record = event["Records"][0]
        if "Sns" in record:
            msg = json.loads(record["Sns"]["Message"])
            return msg["experimentId"]
        if "s3" in record:
            key = record["s3"]["object"]["key"]
            # key format: results/<experiment_id>.json
            return key.split("/")[-1].replace(".json", "")

    # EventBridge / direct invocation
    if "experimentId" in event:
        return event["experimentId"]

    # Weekly summary: generate report for the last 7 days
    if event.get("detailType") == "ScheduledWeeklySummary":
        return "weekly-summary"

    raise ValueError(f"Cannot parse experiment ID from event: {list(event.keys())}")


def _fetch_result(experiment_id: str) -> dict:
    """Fetch experiment result from DynamoDB. Raises on missing item."""
    if experiment_id == "weekly-summary":
        return _build_weekly_summary()

    response = table.get_item(Key={"experimentId": experiment_id})
    item = response.get("Item")
    if not item:
        raise KeyError(f"No DynamoDB record for experimentId={experiment_id}")
    return item


def _build_weekly_summary() -> dict:
    """Scan last 7 days of experiments for a weekly summary record."""
    import time as _time
    cutoff = int(_time.time()) - 7 * 24 * 3600

    response = table.scan(
        FilterExpression="startTime > :cutoff",
        ExpressionAttributeValues={":cutoff": cutoff},
    )
    items = response.get("Items", [])

    passed = sum(1 for i in items if i.get("hypothesisPassed"))
    return {
        "experimentId": "weekly-summary",
        "type":         "weekly-summary",
        "periodDays":   7,
        "totalRuns":    len(items),
        "passed":       passed,
        "failed":       len(items) - passed,
        "experiments":  items,
    }


def _notify_slack(result_data: dict, report_url: str) -> None:
    """Publish a Slack notification message to the SNS topic."""
    if not SNS_TOPIC_ARN:
        _log("warning", "SNS_TOPIC_ARN not set — skipping Slack notification")
        return

    hypothesis_passed = result_data.get("hypothesisPassed", False)
    experiment_id = result_data.get("experimentId", "unknown")
    exp_type = result_data.get("type", "unknown")

    message = {
        "eventType":        "report.generated",
        "experimentId":     experiment_id,
        "experimentType":   exp_type,
        "hypothesisPassed": hypothesis_passed,
        "reportUrl":        report_url,
    }

    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(message),
        Subject=f"Chaos Report: {experiment_id}",
        MessageAttributes={
            "eventType": {"DataType": "String", "StringValue": "report.generated"}
        },
    )
    _log("info", "Slack SNS notification published", experiment_id=experiment_id)
