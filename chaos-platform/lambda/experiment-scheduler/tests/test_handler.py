"""
Unit tests for experiment-scheduler Lambda.
Run: pytest lambda/experiment-scheduler/tests/ -v
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DYNAMODB_TABLE", "chaos-experiments")
os.environ.setdefault("CHAOS_ENGINE_URL", "http://chaos-engine.chaos-engine.svc.cluster.local:8001")
os.environ.setdefault("SLACK_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:chaos-notifications")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


DAILY_EXPERIMENT = {
    "experimentId":       "daily-pod-kill",
    "type":               "pod-kill",
    "scheduleExpression": "daily",
    "targetNamespace":    "chaos-engine",
    "targetLabel":        "app=target-app",
    "durationSeconds":    300,
    "blastRadius":        0.5,
    "enabled":            True,
    "lastRunAt":          0,   # never run
}

RECENT_EXPERIMENT = {
    **DAILY_EXPERIMENT,
    "experimentId": "recently-run",
    "lastRunAt":    int(time.time()) - 1800,   # ran 30 minutes ago
}

DISABLED_EXPERIMENT = {
    **DAILY_EXPERIMENT,
    "experimentId": "disabled-exp",
    "enabled":      False,
}


class TestIsDue:
    def test_daily_experiment_is_due_when_never_run(self):
        from handler import _is_due
        now = datetime.now(tz=timezone.utc)
        assert _is_due(DAILY_EXPERIMENT, now) is True

    def test_recently_run_experiment_is_not_due(self):
        from handler import _is_due
        now = datetime.now(tz=timezone.utc)
        assert _is_due(RECENT_EXPERIMENT, now) is False

    def test_weekly_experiment_due_on_monday(self):
        from handler import _is_due
        # Force Monday
        monday = datetime(2026, 1, 26, 2, 0, tzinfo=timezone.utc)  # a Monday
        weekly_exp = {**DAILY_EXPERIMENT, "scheduleExpression": "weekly"}
        assert _is_due(weekly_exp, monday) is True

    def test_weekly_experiment_not_due_on_tuesday(self):
        from handler import _is_due
        tuesday = datetime(2026, 1, 27, 2, 0, tzinfo=timezone.utc)  # a Tuesday
        weekly_exp = {**DAILY_EXPERIMENT, "scheduleExpression": "weekly"}
        assert _is_due(weekly_exp, tuesday) is False

    def test_weekday_schedule(self):
        from handler import _is_due
        wednesday = datetime(2026, 1, 28, 2, 0, tzinfo=timezone.utc)  # a Wednesday
        mwf_exp = {**DAILY_EXPERIMENT, "scheduleExpression": "Mon,Wed,Fri"}
        assert _is_due(mwf_exp, wednesday) is True

    def test_weekday_schedule_off_day(self):
        from handler import _is_due
        tuesday = datetime(2026, 1, 27, 2, 0, tzinfo=timezone.utc)
        mwf_exp = {**DAILY_EXPERIMENT, "scheduleExpression": "Mon,Wed,Fri"}
        assert _is_due(mwf_exp, tuesday) is False


class TestTriggerExperiment:
    @patch("handler.table")
    @patch("handler.SchedulerClient")
    def test_successful_trigger(self, mock_client_cls, mock_table):
        mock_client = MagicMock()
        mock_client.trigger.return_value = {
            "experimentId": "exp-001", "status": "running"
        }
        mock_client_cls.return_value = mock_client

        from handler import _trigger_experiment
        now = datetime.now(tz=timezone.utc)
        result = _trigger_experiment(DAILY_EXPERIMENT, now)

        assert result["status"] == "triggered"
        assert result["experimentId"] == "daily-pod-kill"
        assert result["attempt"] == 1
        mock_client.trigger.assert_called_once()

    @patch("handler.table")
    @patch("handler.SchedulerClient")
    @patch("handler.time")
    def test_retries_on_failure_then_skips(self, mock_time, mock_client_cls, mock_table):
        mock_time.time.return_value = time.time()
        mock_time.sleep = MagicMock()

        mock_client = MagicMock()
        mock_client.trigger.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_client

        from handler import _trigger_experiment
        now = datetime.now(tz=timezone.utc)
        result = _trigger_experiment(DAILY_EXPERIMENT, now)

        assert result["status"] == "skipped"
        assert mock_client.trigger.call_count == 3   # MAX_RETRIES
        assert mock_time.sleep.call_count == 2        # sleep between retries 1→2, 2→3


class TestLambdaHandler:
    @patch("handler.sns_client")
    @patch("handler.table")
    @patch("handler.SchedulerClient")
    def test_handler_triggers_due_experiments(
        self, mock_client_cls, mock_table, mock_sns
    ):
        mock_table.scan.return_value = {"Items": [DAILY_EXPERIMENT, RECENT_EXPERIMENT]}
        mock_client = MagicMock()
        mock_client.trigger.return_value = {"experimentId": "daily-pod-kill", "status": "running"}
        mock_client_cls.return_value = mock_client

        from handler import lambda_handler
        result = lambda_handler({}, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        # Only DAILY_EXPERIMENT is due, RECENT_EXPERIMENT is not
        assert body["summary"]["triggered"] == 1
        assert body["summary"]["skipped"] == 0

    @patch("handler.sns_client")
    @patch("handler.table")
    @patch("handler.SchedulerClient")
    def test_handler_sends_slack_alert_on_failure(
        self, mock_client_cls, mock_table, mock_sns
    ):
        mock_table.scan.return_value = {"Items": [DAILY_EXPERIMENT]}
        mock_client = MagicMock()
        mock_client.trigger.side_effect = Exception("chaos-engine unreachable")
        mock_client_cls.return_value = mock_client

        from handler import lambda_handler
        with patch("handler.time.sleep"):   # skip sleep in test
            result = lambda_handler({}, {})

        body = json.loads(result["body"])
        assert body["summary"]["skipped"] == 1
        mock_sns.publish.assert_called_once()
        published_msg = json.loads(mock_sns.publish.call_args[1]["Message"])
        assert published_msg["alertName"] == "ExperimentSchedulerFailed"
