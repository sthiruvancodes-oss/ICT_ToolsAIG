from __future__ import annotations

import json
from pathlib import Path

from idops.cli import main
from idops.models import EXIT_OK, EXIT_PLAN_FAILED, EXIT_USAGE

EX_CSV = "examples/people.csv"
EX_DIR = "examples/lab-directory.json"


def test_help_without_command() -> None:
    assert main([]) == EXIT_USAGE


def test_plan_text_ok(capsys) -> None:
    code = main(["plan", "-c", EX_CSV, "-d", EX_DIR])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "OK" in out
    assert "does not call Graph" in out
    assert "alex@lab.example" in out


def test_plan_json_ok(capsys) -> None:
    code = main(["plan", "-c", EX_CSV, "-d", EX_DIR, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["ok"] is True
    assert payload["writes_to_graph"] is False
    assert payload["summary"]["total"] == 3


def test_plan_error_exit_one(tmp_path: Path, capsys) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("action,upn,display_name,groups\njoiner,sam@lab.example,Sam,All Staff\n")
    code = main(["plan", "-c", str(csv_path), "-d", EX_DIR])
    assert code == EXIT_PLAN_FAILED
    assert "already exists" in capsys.readouterr().out


def test_apply_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "after.json"
    code = main(["apply", "-c", EX_CSV, "-d", EX_DIR, "-o", str(out)])
    assert code == EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))
    upns = {user["upn"] for user in payload["users"]}
    assert "alex@lab.example" in upns
    original = json.loads(Path(EX_DIR).read_text(encoding="utf-8"))
    assert "alex@lab.example" not in {user["upn"] for user in original["users"]}


def test_missing_csv() -> None:
    assert main(["plan", "-c", "missing.csv", "-d", EX_DIR]) == EXIT_USAGE


def test_apply_refuses_on_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("action,upn\nleaver,ghost@lab.example\n")
    out = tmp_path / "after.json"
    code = main(["apply", "-c", str(csv_path), "-d", EX_DIR, "-o", str(out)])
    assert code == EXIT_PLAN_FAILED
    assert not out.exists()
