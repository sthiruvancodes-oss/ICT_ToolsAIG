from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from nethealth.config import parse_suite
from nethealth.models import CheckResult
from nethealth.runner import run_suite


def test_run_suite_preserves_order() -> None:
    suite = parse_suite(
        {
            "name": "order",
            "checks": [
                {"name": "a", "type": "icmp", "host": "127.0.0.1"},
                {"name": "b", "type": "dns", "query": "localhost"},
            ],
        }
    )

    def fake_probe(spec, timeout, warn_tls_days):
        return CheckResult(spec.name, spec.type, spec.name, "pass", "ok", 1.0)

    with patch("nethealth.runner.run_probe", side_effect=fake_probe):
        summary = run_suite(suite, jobs=4)
    assert [item.name for item in summary.results] == ["a", "b"]
    assert summary.ok
    assert summary.started_at.tzinfo is timezone.utc
