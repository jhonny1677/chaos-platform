"""
ReportBuilder — Converts raw DynamoDB experiment data into a styled HTML report.

All CSS is inline because WeasyPrint renders CSS differently from browsers
and does not support external stylesheets loaded from the filesystem.
The class reads the HTML template file and substitutes data sections.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_PATH = Path(__file__).parent / "template" / "report-template.html"

# Colour constants (used inline throughout the report)
GREEN   = "#22c55e"
RED     = "#ef4444"
YELLOW  = "#f59e0b"
BLUE    = "#3b82f6"
GREY    = "#6b7280"
DARK    = "#111827"
SURFACE = "#1f2937"
BORDER  = "#374151"


def _esc(value: Any) -> str:
    """HTML-escape any value for safe insertion into the template."""
    return html.escape(str(value) if value is not None else "—")


def _ts(unix: int | None) -> str:
    """Format a Unix timestamp as a human-readable UTC string."""
    if not unix:
        return "—"
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _duration(start: int | None, end: int | None) -> str:
    if not start or not end:
        return "—"
    seconds = end - start
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


class ReportBuilder:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.report_type = data.get("type", "experiment")
        self.passed = bool(data.get("hypothesisPassed", False))

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self) -> str:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        if self.report_type == "weekly-summary":
            body = self._weekly_summary_body()
        elif self.report_type == "load-test":
            body = self._load_test_body()
        else:
            body = self._experiment_body()

        status_color = GREEN if self.passed else RED
        status_text  = "HYPOTHESIS PASSED" if self.passed else "HYPOTHESIS FAILED"
        experiment_id = _esc(self.data.get("experimentId", "unknown"))

        return (template
                .replace("{{EXPERIMENT_ID}}", experiment_id)
                .replace("{{STATUS_COLOR}}", status_color)
                .replace("{{STATUS_TEXT}}", status_text)
                .replace("{{GENERATED_AT}}", datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
                .replace("{{REPORT_BODY}}", body))

    # ── Report body sections ──────────────────────────────────────────────────

    def _experiment_body(self) -> str:
        d = self.data
        sections = [
            self._section_executive_summary(d),
            self._section_timeline(d),
            self._section_metrics(d),
            self._section_hypothesis(d),
            self._section_recommendations(d),
        ]
        return "\n".join(sections)

    def _load_test_body(self) -> str:
        d = self.data
        sections = [
            self._section_load_summary(d),
            self._section_load_metrics(d),
            self._section_slo_analysis(d),
            self._section_recommendations(d),
        ]
        return "\n".join(sections)

    def _weekly_summary_body(self) -> str:
        d = self.data
        experiments = d.get("experiments", [])
        rows = ""
        for exp in sorted(experiments, key=lambda e: e.get("startTime", 0), reverse=True):
            passed = exp.get("hypothesisPassed", False)
            color  = GREEN if passed else RED
            rows += f"""
            <tr>
              <td style="padding:10px;border-bottom:1px solid {BORDER};">{_esc(exp.get("experimentId",""))}</td>
              <td style="padding:10px;border-bottom:1px solid {BORDER};">{_esc(exp.get("type",""))}</td>
              <td style="padding:10px;border-bottom:1px solid {BORDER};">{_ts(exp.get("startTime"))}</td>
              <td style="padding:10px;border-bottom:1px solid {BORDER};color:{color};font-weight:bold;">
                {"✓ PASSED" if passed else "✗ FAILED"}
              </td>
            </tr>"""

        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">7-Day Experiment Summary</h2>
          <div style="display:flex;gap:32px;margin-bottom:24px;">
            <div style="text-align:center;">
              <div style="font-size:36px;font-weight:bold;color:white;">{d.get("totalRuns",0)}</div>
              <div style="color:{GREY};">Total Runs</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:36px;font-weight:bold;color:{GREEN};">{d.get("passed",0)}</div>
              <div style="color:{GREY};">Passed</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:36px;font-weight:bold;color:{RED};">{d.get("failed",0)}</div>
              <div style="color:{GREY};">Failed</div>
            </div>
          </div>
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr style="color:{GREY};text-align:left;">
                <th style="padding:10px;">Experiment ID</th>
                <th style="padding:10px;">Type</th>
                <th style="padding:10px;">Started</th>
                <th style="padding:10px;">Result</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    # ── Section helpers ───────────────────────────────────────────────────────

    def _section_executive_summary(self, d: dict) -> str:
        duration = _duration(d.get("startTime"), d.get("endTime"))
        target   = _esc(d.get("targetNamespace", "—")) + "/" + _esc(d.get("targetLabel", "—"))
        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">Executive Summary</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="color:{GREY};padding:8px 0;width:200px;">Experiment Type</td>
                <td style="color:white;">{_esc(d.get("type","—"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Target</td>
                <td style="color:white;">{target}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Started</td>
                <td style="color:white;">{_ts(d.get("startTime"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Completed</td>
                <td style="color:white;">{_ts(d.get("endTime"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Duration</td>
                <td style="color:white;">{duration}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Pods Targeted</td>
                <td style="color:white;">{_esc(d.get("podsTargeted","—"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Pods Affected</td>
                <td style="color:white;">{_esc(d.get("podsAffected","—"))}</td></tr>
          </table>
        </div>"""

    def _section_timeline(self, d: dict) -> str:
        events = d.get("events", [])
        rows = ""
        for ev in sorted(events, key=lambda e: e.get("timestamp", 0)):
            rows += f"""
            <tr>
              <td style="padding:8px 0;color:{GREY};white-space:nowrap;">{_ts(ev.get("timestamp"))}</td>
              <td style="padding:8px 16px;color:white;">{_esc(ev.get("type",""))}</td>
              <td style="padding:8px 0;color:{GREY};">{_esc(ev.get("detail",""))}</td>
            </tr>"""

        if not rows:
            rows = f'<tr><td colspan="3" style="color:{GREY};padding:16px;">No events recorded.</td></tr>'

        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">Timeline of Events</h2>
          <table style="width:100%;border-collapse:collapse;">{rows}</table>
        </div>"""

    def _section_metrics(self, d: dict) -> str:
        m = d.get("metrics", {})
        before  = m.get("before", {})
        during  = m.get("during", {})
        after   = m.get("after", {})

        def row(label, key, unit=""):
            b = before.get(key, "—")
            dr = during.get(key, "—")
            a  = after.get(key, "—")
            return f"""
            <tr>
              <td style="padding:10px;color:{GREY};border-bottom:1px solid {BORDER};">{label}</td>
              <td style="padding:10px;color:white;text-align:center;border-bottom:1px solid {BORDER};">{b}{unit}</td>
              <td style="padding:10px;color:{YELLOW};text-align:center;border-bottom:1px solid {BORDER};">{dr}{unit}</td>
              <td style="padding:10px;color:white;text-align:center;border-bottom:1px solid {BORDER};">{a}{unit}</td>
            </tr>"""

        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">Metrics Comparison</h2>
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr style="color:{GREY};">
                <th style="padding:10px;text-align:left;">Metric</th>
                <th style="padding:10px;text-align:center;">Before</th>
                <th style="padding:10px;text-align:center;color:{YELLOW};">During Chaos</th>
                <th style="padding:10px;text-align:center;">After</th>
              </tr>
            </thead>
            <tbody>
              {row("Error Rate",    "errorRate",   "%")}
              {row("p50 Latency",   "p50LatencyMs", "ms")}
              {row("p99 Latency",   "p99LatencyMs", "ms")}
              {row("Requests/sec",  "rps")}
              {row("Available Pods","availablePods")}
            </tbody>
          </table>
        </div>"""

    def _section_hypothesis(self, d: dict) -> str:
        h      = d.get("hypothesis", {})
        passed = self.passed
        color  = GREEN if passed else RED
        icon   = "✓" if passed else "✗"
        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;
                    border-left:4px solid {color};">
          <h2 style="color:white;margin:0 0 16px 0;">Hypothesis Result</h2>
          <div style="font-size:24px;font-weight:bold;color:{color};margin-bottom:16px;">
            {icon} {("HYPOTHESIS PASSED" if passed else "HYPOTHESIS FAILED")}
          </div>
          <div style="color:{GREY};margin-bottom:8px;">Hypothesis Statement:</div>
          <div style="color:white;font-style:italic;margin-bottom:16px;">
            "{_esc(h.get("statement","No hypothesis recorded."))}"
          </div>
          <div style="color:{GREY};margin-bottom:8px;">Measured Value:</div>
          <div style="color:white;">{_esc(h.get("measuredValue","—"))}</div>
          <div style="color:{GREY};margin-top:8px;">Threshold:</div>
          <div style="color:white;">{_esc(h.get("threshold","—"))}</div>
        </div>"""

    def _section_load_metrics(self, d: dict) -> str:
        m = d.get("metrics", {})
        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">Load Test Metrics</h2>
          <div style="display:flex;gap:24px;flex-wrap:wrap;">
            {self._metric_card("Peak RPS",     m.get("peakRps","—"),     BLUE)}
            {self._metric_card("Avg RPS",      m.get("avgRps","—"),      GREY)}
            {self._metric_card("p50 Latency",  f'{m.get("p50LatencyMs","—")}ms', GREEN)}
            {self._metric_card("p99 Latency",  f'{m.get("p99LatencyMs","—")}ms', YELLOW)}
            {self._metric_card("Error Rate",   f'{m.get("errorRate","—")}%',     RED)}
            {self._metric_card("Total Requests", m.get("totalRequests","—"), GREY)}
          </div>
        </div>"""

    def _section_load_summary(self, d: dict) -> str:
        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">Load Test Summary</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="color:{GREY};padding:8px 0;width:200px;">Scenario</td>
                <td style="color:white;">{_esc(d.get("scenario","—"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Target URL</td>
                <td style="color:white;">{_esc(d.get("targetUrl","—"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Duration</td>
                <td style="color:white;">{_duration(d.get("startTime"),d.get("endTime"))}</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Workers</td>
                <td style="color:white;">{_esc(d.get("workerCount","—"))}</td></tr>
          </table>
        </div>"""

    def _section_slo_analysis(self, d: dict) -> str:
        slo  = d.get("sloResults", {})
        avail_ok  = slo.get("availabilitySLOMet", None)
        latency_ok = slo.get("latencySLOMet", None)

        def badge(ok):
            if ok is None:
                return f'<span style="color:{GREY};">N/A</span>'
            c = GREEN if ok else RED
            t = "MET" if ok else "BREACHED"
            return f'<span style="color:{c};font-weight:bold;">{t}</span>'

        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;">
          <h2 style="color:white;margin:0 0 16px 0;">SLO Analysis</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="color:{GREY};padding:8px 0;width:250px;">Availability SLO (≥99.5%)</td>
                <td>{badge(avail_ok)}</td>
                <td style="color:{GREY};">{_esc(slo.get("availabilityActual",""))}%</td></tr>
            <tr><td style="color:{GREY};padding:8px 0;">Latency SLO (p99 &lt;500ms)</td>
                <td>{badge(latency_ok)}</td>
                <td style="color:{GREY};">{_esc(slo.get("p99LatencyActual",""))}ms</td></tr>
          </table>
        </div>"""

    def _section_recommendations(self, d: dict) -> str:
        passed = self.passed
        recs   = d.get("recommendations", [])

        if not recs and not passed:
            recs = self._auto_recommendations(d)

        if not recs:
            content = f'<p style="color:{GREY};">No issues detected. The system demonstrated resilience as expected.</p>'
        else:
            items = "".join(
                f'<li style="color:white;margin-bottom:8px;">{_esc(r)}</li>' for r in recs
            )
            content = f'<ul style="margin:0;padding-left:20px;">{items}</ul>'

        header_color = GREEN if passed else RED
        return f"""
        <div style="background:{SURFACE};border-radius:8px;padding:24px;margin-bottom:24px;
                    border-left:4px solid {header_color};">
          <h2 style="color:white;margin:0 0 16px 0;">Recommendations</h2>
          {content}
        </div>"""

    def _auto_recommendations(self, d: dict) -> list[str]:
        """Generate recommendations based on the failure type."""
        failure_type = d.get("failureType", "")
        recs = []
        if "pod-kill" in failure_type:
            recs.append("Increase pod replicas (minReplicas ≥ 2) so a single pod loss does not reduce capacity below the SLO threshold.")
            recs.append("Add a PodDisruptionBudget to ensure at least one pod is always available during voluntary disruptions.")
            recs.append("Review readinessProbe thresholds — slow readiness causes traffic to drop during pod restart.")
        if "network" in failure_type:
            recs.append("Add retry logic with exponential backoff in the HTTP client (at least 3 retries with jitter).")
            recs.append("Implement circuit breaker pattern so downstream failures don't cascade upstream.")
        if "cpu" in failure_type or "memory" in failure_type:
            recs.append("Set CPU/memory resource limits that match observed peak usage with 20% headroom.")
            recs.append("Configure HPA to scale before the resource threshold is reached (targetUtilization: 70%).")
        if not recs:
            recs.append("Review the hypothesis definition — ensure the threshold reflects your actual SLO targets.")
            recs.append("Consider increasing chaos blast radius gradually (start at 10%, not 50%) to build confidence.")
        return recs

    @staticmethod
    def _metric_card(label: str, value: Any, color: str) -> str:
        return f"""
        <div style="background:{DARK};border-radius:6px;padding:16px;min-width:140px;text-align:center;">
          <div style="font-size:28px;font-weight:bold;color:{color};">{_esc(value)}</div>
          <div style="color:{GREY};font-size:13px;margin-top:4px;">{_esc(label)}</div>
        </div>"""
