"""
Unit tests for report-generator Lambda.

Tests use moto for AWS service mocking and unittest.mock for Slack SNS.
Run: pytest lambda/report-generator/tests/ -v
"""

from __future__ import annotations

import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ── Stub out WeasyPrint so tests don't require the native library ─────────────
weasyprint_stub = types.ModuleType("weasyprint")
weasyprint_stub.HTML = MagicMock()
weasyprint_stub.CSS = MagicMock()
sys.modules.setdefault("weasyprint", weasyprint_stub)
sys.modules.setdefault("weasyprint.text", types.ModuleType("weasyprint.text"))
sys.modules.setdefault(
    "weasyprint.text.fonts", types.ModuleType("weasyprint.text.fonts")
)

# Set required env vars before importing the handler
os.environ.setdefault("DYNAMODB_TABLE", "chaos-experiments")
os.environ.setdefault("REPORTS_BUCKET", "chaos-reports-test")
os.environ.setdefault("SLACK_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:chaos-notifications")

# Add lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_EXPERIMENT = {
    "experimentId": "exp-2026-001",
    "type":         "pod-kill",
    "hypothesisPassed": True,
    "targetNamespace":  "chaos-engine",
    "targetLabel":      "app=target-app",
    "startTime":        1719446400,
    "endTime":          1719447000,
    "podsTargeted":     3,
    "podsAffected":     2,
    "metrics": {
        "before":  {"errorRate": 0.1, "p50LatencyMs": 45, "p99LatencyMs": 180},
        "during":  {"errorRate": 2.3, "p50LatencyMs": 89, "p99LatencyMs": 450},
        "after":   {"errorRate": 0.1, "p50LatencyMs": 46, "p99LatencyMs": 182},
    },
    "hypothesis": {
        "statement":    "Error rate stays below 5% during pod kill",
        "measuredValue": "2.3%",
        "threshold":    "5%",
    },
    "events": [
        {"timestamp": 1719446400, "type": "experiment.started", "detail": "Pod kill initiated"},
        {"timestamp": 1719446600, "type": "pod.killed",         "detail": "Killed target-app-abc12"},
        {"timestamp": 1719447000, "type": "experiment.completed","detail": "All pods recovered"},
    ],
}

SNS_EVENT = {
    "Records": [{
        "EventSource": "aws:sns",
        "Sns": {
            "Message": json.dumps({"experimentId": "exp-2026-001"}),
        },
    }]
}

S3_EVENT = {
    "Records": [{
        "eventSource": "aws:s3",
        "s3": {
            "object": {"key": "results/exp-2026-001.json"},
        },
    }]
}

DIRECT_EVENT = {"experimentId": "exp-2026-001"}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestParseExperimentId:
    def setup_method(self):
        import handler
        self.handler = handler

    def test_parse_from_sns(self):
        from handler import _parse_experiment_id
        assert _parse_experiment_id(SNS_EVENT) == "exp-2026-001"

    def test_parse_from_s3(self):
        from handler import _parse_experiment_id
        assert _parse_experiment_id(S3_EVENT) == "exp-2026-001"

    def test_parse_from_direct(self):
        from handler import _parse_experiment_id
        assert _parse_experiment_id(DIRECT_EVENT) == "exp-2026-001"

    def test_unknown_event_raises(self):
        from handler import _parse_experiment_id
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_experiment_id({"unknown": "shape"})


class TestLambdaHandler:
    @patch("handler.S3Uploader")
    @patch("handler.PDFGenerator")
    @patch("handler.ReportBuilder")
    @patch("handler.table")
    @patch("handler.sns_client")
    def test_successful_invocation(
        self, mock_sns, mock_table, mock_builder_cls, mock_pdf_cls, mock_uploader_cls
    ):
        # Arrange
        mock_table.get_item.return_value = {"Item": SAMPLE_EXPERIMENT}
        mock_builder = MagicMock()
        mock_builder.build.return_value = "<html>report</html>"
        mock_builder_cls.return_value = mock_builder

        mock_pdf = MagicMock()
        mock_pdf.to_pdf.return_value = b"%PDF-1.4 fake"
        mock_pdf_cls.return_value = mock_pdf

        mock_uploader = MagicMock()
        mock_uploader.upload.return_value = "https://s3.example.com/signed-url"
        mock_uploader_cls.return_value = mock_uploader

        # Act
        from handler import lambda_handler
        result = lambda_handler(DIRECT_EVENT, {})

        # Assert
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["experimentId"] == "exp-2026-001"
        assert "reportUrl" in body
        mock_table.get_item.assert_called_once_with(Key={"experimentId": "exp-2026-001"})
        mock_builder_cls.assert_called_once_with(SAMPLE_EXPERIMENT)
        mock_pdf.to_pdf.assert_called_once_with("<html>report</html>")

    @patch("handler.table")
    def test_missing_dynamo_record_returns_400(self, mock_table):
        mock_table.get_item.return_value = {}  # no "Item"
        from handler import lambda_handler
        result = lambda_handler(DIRECT_EVENT, {})
        assert result["statusCode"] == 400


class TestReportBuilder:
    def test_build_returns_html_string(self):
        # Requires template file to be present
        from report_builder import ReportBuilder
        html_output = ReportBuilder(SAMPLE_EXPERIMENT).build()
        assert isinstance(html_output, str)
        assert "exp-2026-001" in html_output
        assert "HYPOTHESIS PASSED" in html_output

    def test_failed_hypothesis_shows_red(self):
        from report_builder import ReportBuilder
        failed_data = {**SAMPLE_EXPERIMENT, "hypothesisPassed": False}
        html_output = ReportBuilder(failed_data).build()
        assert "HYPOTHESIS FAILED" in html_output

    def test_auto_recommendations_generated_for_failed(self):
        from report_builder import ReportBuilder
        failed_data = {
            **SAMPLE_EXPERIMENT,
            "hypothesisPassed": False,
            "failureType": "pod-kill",
        }
        builder = ReportBuilder(failed_data)
        recs = builder._auto_recommendations(failed_data)
        assert len(recs) > 0
        assert any("replicas" in r.lower() for r in recs)


class TestS3Uploader:
    @patch("s3_uploader.boto3.client")
    def test_upload_and_presign(self, mock_boto3_client):
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://signed-url"

        from s3_uploader import S3Uploader
        uploader = S3Uploader("test-bucket")
        url = uploader.upload("reports/test.pdf", b"PDF bytes")

        assert url == "https://signed-url"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "application/pdf"
        assert call_kwargs["ServerSideEncryption"] == "AES256"
