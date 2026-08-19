from __future__ import annotations

import json
from datetime import datetime, timezone

from nethealth.models import CheckResult, RunSummary
from nethealth.report import render


def _summary(*results: CheckResult) -> RunSummary:
    return RunSummary(
        name="lab",
        started_at=datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc),
        duration_ms=12.5,
        results=results,
    )


def test_json_report_shape() -> None:
    summary = _summary(
        CheckResult("ping", "icmp", "127.0.0.1", "pass", "echo reply received", 1.2),
        CheckResult("ssh", "tcp", "127.0.0.1:22", "fail", "Connection refused", 3.0),
    )
    payload = json.loads(render(summary, "json"))
    assert payload["name"] == "lab"
    assert payload["ok"] is False
    assert payload["summary"]["fail"] == 1
    assert payload["results"][0]["status"] == "pass"


def test_text_report_includes_outcome() -> None:
    summary = _summary(CheckResult("ping", "icmp", "127.0.0.1", "pass", "ok", 1.0))
    text = render(summary, "text")
    assert "OK" in text
    assert "loopback" not in text
    assert "ping" in text
    assert "PASS" in text


def test_html_escapes_and_marks_failed() -> None:
    summary = _summary(
        CheckResult("x", "http", "http://x", "fail", "<script>alert(1)</script>", 1.0),
    )
    body = render(summary, "html")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    assert "FAILED" in body
    assert 'class="fail"' in body
