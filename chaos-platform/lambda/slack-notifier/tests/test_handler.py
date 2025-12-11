"""
Unit tests for slack-notifier Lambda.
Run: pytest lambda/slack-notifier/tests/ -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/TEST/TEST/TEST")
os.environ.setdefault("SLACK_DEFAULT_CHANNEL", "#test-alerts")
os.environ.setdefault("CHANNEL_EXPERIMENTS", "#test-experiments")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _sns_event(event_type: str, body: dict) -> dict:
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps(body),
                "MessageAttributes": {
                    "eventType": {"Type": "String", "Value": event_type}
                },
            }
        }]
    }


class TestHandler:
    @patch("handler.SlackClient")
    def test_experiment_started_routes_correctly(self, mock_slack_cls):
        mock_slack = MagicMock()
        mock_slack.post.return_value = True
        mock_slack_cls.return_value = mock_slack

        from handler import lambda_handler
        event = _sns_event("experiment.started", {
            "experimentId": "exp-001",
            "type": "pod-kill",
            "targetNamespace": "chaos-engine",
        })
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200
        mock_slack.post.assert_called_once()
        call_kwargs = mock_slack.post.call_args[1]
        assert call_kwargs["channel"] == "#test-experiments"

    @patch("handler.SlackClient")
    def test_unknown_event_type_is_skipped(self, mock_slack_cls):
        from handler import lambda_handler
        event = _sns_event("unknown.event.type", {"foo": "bar"})
        result = lambda_handler(event, {})
        # Should not raise, should return 207 (partial success)
        mock_slack_cls.return_value.post.assert_not_called()

    @patch("handler.SlackClient")
    def test_multiple_records_processed(self, mock_slack_cls):
        mock_slack = MagicMock()
        mock_slack.post.return_value = True
        mock_slack_cls.return_value = mock_slack

        from handler import lambda_handler
        event = {
            "Records": [
                _sns_event("experiment.started", {"experimentId": "exp-001"})["Records"][0],
                _sns_event("experiment.completed", {"experimentId": "exp-001", "hypothesisPassed": True})["Records"][0],
            ]
        }
        result = lambda_handler(event, {})
        assert mock_slack.post.call_count == 2


class TestMessageFormatter:
    def setup_method(self):
        from message_formatter import MessageFormatter
        self.fmt = MessageFormatter()

    def test_experiment_started_blocks(self):
        blocks = self.fmt.format_experiment_started({
            "experimentId": "exp-001",
            "type": "pod-kill",
            "targetNamespace": "chaos-engine",
            "targetLabel": "app=target-app",
            "expectedDurationSeconds": 300,
        })
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        # First block should be a header
        assert blocks[0]["type"] == "header"
        text = blocks[0]["text"]["text"]
        assert "Started" in text

    def test_experiment_completed_passed(self):
        blocks = self.fmt.format_experiment_completed({
            "experimentId": "exp-001",
            "hypothesisPassed": True,
            "metrics": {"during": {"errorRate": 1.2, "p99LatencyMs": 180}},
        })
        header_text = blocks[0]["text"]["text"]
        assert "PASSED" in header_text

    def test_experiment_completed_failed(self):
        blocks = self.fmt.format_experiment_completed({
            "experimentId": "exp-001",
            "hypothesisPassed": False,
            "metrics": {"during": {}},
        })
        header_text = blocks[0]["text"]["text"]
        assert "FAILED" in header_text

    def test_alert_fired_includes_grafana_button(self):
        blocks = self.fmt.format_alert_fired({
            "alertName": "TargetAppHighErrorRate",
            "severity": "critical",
            "description": "Error rate > 5% for 2m",
            "grafanaUrl": "https://grafana.example.com/d/abc",
        })
        # Should have a button block
        button_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(button_blocks) == 1
        assert "grafana.example.com" in button_blocks[0]["elements"][0]["url"]

    def test_load_test_slo_met(self):
        blocks = self.fmt.format_load_test_completed({
            "scenario": "spike",
            "sloMet": True,
            "peakRps": 1200,
            "p99LatencyMs": 320,
            "errorRate": 0.2,
        })
        assert any("MET" in str(b) for b in blocks)


class TestSlackClient:
    def test_post_success(self):
        from slack_client import SlackClient
        client = SlackClient("https://hooks.slack.com/test")
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"ok"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            result = client.post(channel="#test", text="hello", blocks=[])
            assert result is True

    def test_post_slack_error_returns_false(self):
        from slack_client import SlackClient
        import urllib.error
        client = SlackClient("https://hooks.slack.com/test")
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"channel_not_found"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            result = client.post(channel="#test", text="hello")
            assert result is False
