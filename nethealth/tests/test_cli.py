from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nethealth.cli import main
from nethealth.models import (
    EXIT_CHECKS_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    CheckResult,
    RunSummary,
)


def _ok_summary() -> RunSummary:
    return RunSummary(
        name="lab",
        started_at=datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc),
        duration_ms=4.0,
        results=(CheckResult("ping", "icmp", "127.0.0.1", "pass", "ok", 1.0),),
    )


def _fail_summary() -> RunSummary:
    return RunSummary(
        name="lab",
        started_at=datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc),
        duration_ms=4.0,
        results=(CheckResult("ssh", "tcp", "127.0.0.1:22", "fail", "refused", 1.0),),
    )


def test_help_without_command() -> None:
    assert main([]) == EXIT_USAGE


def test_missing_targets() -> None:
    assert main(["check"]) == EXIT_USAGE


def test_check_json_exit_zero(capsys) -> None:
    with patch("nethealth.cli.run_suite", return_value=_ok_summary()):
        code = main(["check", "--icmp", "127.0.0.1", "--format", "json"])
    assert code == EXIT_OK
    payload = capsys.readouterr().out
    assert '"ok": true' in payload


def test_check_fail_exit_one(capsys) -> None:
    with patch("nethealth.cli.run_suite", return_value=_fail_summary()):
        code = main(["check", "--tcp", "127.0.0.1:22"])
    assert code == EXIT_CHECKS_FAILED
    assert "FAILED" in capsys.readouterr().out


def test_writes_html_file(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    with patch("nethealth.cli.run_suite", return_value=_ok_summary()):
        code = main(["check", "--icmp", "127.0.0.1", "--format", "html", "-o", str(out)])
    assert code == EXIT_OK
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "nethealth" in text


def test_config_file_not_found() -> None:
    assert main(["check", "-c", "missing.toml"]) == EXIT_USAGE


@pytest.mark.parametrize("timeout", ["0", "-5"])
def test_non_positive_timeout_rejected(timeout: str, tmp_path: Path) -> None:
    suite = tmp_path / "suite.toml"
    suite.write_text(
        'name = "x"\n[[checks]]\nname = "a"\ntype = "icmp"\nhost = "127.0.0.1"\n',
        encoding="utf-8",
    )
    assert main(["check", "-c", str(suite), "--timeout", timeout]) == EXIT_USAGE


@pytest.mark.parametrize("jobs", ["0", "-3"])
def test_non_positive_jobs_rejected(jobs: str) -> None:
    assert main(["check", "--icmp", "127.0.0.1", "--jobs", jobs]) == EXIT_USAGE


def test_unwritable_output_reports_usage_error(tmp_path: Path, capsys) -> None:
    target = tmp_path / "missing-dir" / "report.html"
    with patch("nethealth.cli.run_suite", return_value=_ok_summary()):
        code = main(["check", "--icmp", "127.0.0.1", "--format", "html", "-o", str(target)])
    assert code == EXIT_USAGE
    assert "cannot write" in capsys.readouterr().err


def test_cli_check_cannot_reuse_a_config_check_name(tmp_path: Path, capsys) -> None:
    suite = tmp_path / "suite.toml"
    suite.write_text(
        'name = "x"\n[[checks]]\nname = "icmp-1"\ntype = "icmp"\nhost = "127.0.0.1"\n',
        encoding="utf-8",
    )
    code = main(["check", "-c", str(suite), "--icmp", "127.0.0.1"])
    assert code == EXIT_USAGE
    assert "duplicate check name" in capsys.readouterr().err


def test_keyboard_interrupt_exits_130(capsys) -> None:
    with patch("nethealth.cli.run_suite", side_effect=KeyboardInterrupt):
        code = main(["check", "--icmp", "127.0.0.1"])
    assert code == EXIT_INTERRUPTED
    assert "interrupted" in capsys.readouterr().err


def test_broken_pipe_is_not_a_traceback() -> None:
    # os.dup2 is stubbed out because the real call would retarget pytest's capture fd.
    with patch("nethealth.cli.run_suite", return_value=_ok_summary()), patch.object(
        sys.stdout, "write", side_effect=BrokenPipeError
    ), patch("nethealth.cli.os.dup2") as dup2:
        code = main(["check", "--icmp", "127.0.0.1"])
    assert code == EXIT_INTERRUPTED
    assert dup2.called
