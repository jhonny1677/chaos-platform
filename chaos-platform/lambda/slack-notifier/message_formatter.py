"""
MessageFormatter — Builds Slack Block Kit message payloads for each event type.

Slack Block Kit docs: https://api.slack.com/block-kit
Each method returns a list of block objects that can be passed directly to the
Slack API. Rich formatting (bold, code, emoji) is achieved using mrkdwn syntax.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _ts(unix: int | None) -> str:
    if not unix:
        return "—"
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _dur(seconds: int | None) -> str:
    if not seconds:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _fields(*pairs: tuple[str, str]) -> dict:
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
            for label, value in pairs
        ],
    }


def _divider() -> dict:
    return {"type": "divider"}


def _button(text: str, url: str, style: str = "primary") -> dict:
    return {
        "type": "actions",
        "elements": [{
            "type":  "button",
            "style": style,
            "text":  {"type": "plain_text", "text": text, "emoji": True},
            "url":   url,
        }],
    }


class MessageFormatter:

    def format_experiment_started(self, body: dict) -> list[dict]:
        exp_id    = body.get("experimentId", "unknown")
        exp_type  = body.get("type", "unknown")
        target    = body.get("targetNamespace", "?") + "/" + body.get("targetLabel", "?")
        duration  = body.get("expectedDurationSeconds")

        return [
            _header("⚡ Chaos Experiment Started"),
            _section(f"Experiment `{exp_id}` is now running."),
            _fields(
                ("Experiment Type",  f"`{exp_type}`"),
                ("Target",           f"`{target}`"),
                ("Expected Duration", _dur(duration)),
                ("Started At",       _ts(body.get("startTime"))),
            ),
            _divider(),
            _section("_Monitor in real-time on the Grafana dashboard during the experiment._"),
        ]

    def format_experiment_completed(self, body: dict) -> list[dict]:
        exp_id   = body.get("experimentId", "unknown")
        passed   = body.get("hypothesisPassed", False)
        icon     = "✅" if passed else "❌"
        result   = "PASSED" if passed else "FAILED"
        color_kw = "good" if passed else "danger"  # for attachment fallback

        metrics = body.get("metrics", {}).get("during", {})
        report_url = body.get("reportUrl", "")

        blocks = [
            _header(f"{icon} Experiment {result}: {exp_id}"),
            _section(
                f"The system *{'maintained' if passed else 'did NOT maintain'}* its "
                f"hypothesis during chaos injection."
            ),
            _fields(
                ("Type",         f"`{body.get('type', '—')}`"),
                ("Duration",     _dur(body.get("durationSeconds"))),
                ("Error Rate",   f"{metrics.get('errorRate', '—')}%"),
                ("p99 Latency",  f"{metrics.get('p99LatencyMs', '—')}ms"),
            ),
            _divider(),
        ]

        if report_url:
            blocks.append(_button("📄 View Full Report", report_url))

        return blocks

    def format_experiment_failed(self, body: dict) -> list[dict]:
        exp_id  = body.get("experimentId", "unknown")
        reason  = body.get("errorReason", "Unknown error")
        phase   = body.get("failedPhase", "unknown")
        return [
            _header("🔥 Experiment Errored Out"),
            _section(
                f"Experiment `{exp_id}` crashed during the *{phase}* phase and could not complete.\n"
                f"The hypothesis could not be evaluated."
            ),
            _fields(
                ("Experiment ID", f"`{exp_id}`"),
                ("Failed Phase",  phase),
                ("Error",         f"```{reason}```"),
            ),
            _divider(),
            _section("_Check chaos-engine pod logs for the full stack trace._"),
        ]

    def format_load_test_completed(self, body: dict) -> list[dict]:
        scenario = body.get("scenario", "unknown")
        peak_rps = body.get("peakRps", "—")
        p99      = body.get("p99LatencyMs", "—")
        err_rate = body.get("errorRate", "—")
        slo_met  = body.get("sloMet", None)

        icon = "✅" if slo_met else ("❌" if slo_met is False else "📊")

        return [
            _header(f"{icon} Load Test Completed: {scenario}"),
            _section(f"Scenario `{scenario}` has finished. SLO: *{'MET' if slo_met else 'BREACHED' if slo_met is False else 'N/A'}*"),
            _fields(
                ("Peak RPS",      str(peak_rps)),
                ("p99 Latency",   f"{p99}ms"),
                ("Error Rate",    f"{err_rate}%"),
                ("Total Workers", str(body.get("workerCount", "—"))),
            ),
            _divider(),
            _section(f"Duration: {_dur(body.get('durationSeconds'))} | Started: {_ts(body.get('startTime'))}"),
        ]

    def format_alert_fired(self, body: dict) -> list[dict]:
        alert_name  = body.get("alertName", "Unknown Alert")
        severity    = body.get("severity", "warning").upper()
        description = body.get("description", "No description provided.")
        grafana_url = body.get("grafanaUrl", "")

        icon = {"CRITICAL": "🚨", "ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}.get(severity, "⚠️")

        blocks = [
            _header(f"{icon} Alert: {alert_name}"),
            _fields(
                ("Severity",   f"`{severity}`"),
                ("Fired At",   _ts(body.get("firedAt"))),
            ),
            _section(f"*Description:*\n{description}"),
            _divider(),
        ]

        if grafana_url:
            blocks.append(_button("📈 View in Grafana", grafana_url))

        return blocks

    def format_report_generated(self, body: dict) -> list[dict]:
        exp_id     = body.get("experimentId", "unknown")
        passed     = body.get("hypothesisPassed", None)
        report_url = body.get("reportUrl", "")

        icon = "✅" if passed else "❌" if passed is False else "📄"

        blocks = [
            _header("📄 Experiment Report Ready"),
            _section(f"PDF report for experiment `{exp_id}` has been generated."),
            _fields(
                ("Experiment",        f"`{exp_id}`"),
                ("Hypothesis Result", f"{icon} {'PASSED' if passed else 'FAILED' if passed is False else 'N/A'}"),
            ),
        ]

        if report_url:
            blocks.append(_button("📥 Download PDF Report (valid 7 days)", report_url))

        return blocks
