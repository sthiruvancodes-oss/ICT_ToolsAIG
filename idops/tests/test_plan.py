from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from idops.csv_load import parse_people
from idops.directory import parse_directory
from idops.models import Directory
from idops.plan import apply_plan, build_plan

NOW = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)


def _lab() -> Directory:
    return parse_directory(
        {
            "tenant": "lab",
            "groups": ["All Staff", "Finance", "Operations", "Warehouse", "Disabled Users"],
            "users": [
                {
                    "upn": "sam@lab.example",
                    "display_name": "Sam Ortiz",
                    "department": "Finance",
                    "title": "Analyst",
                    "enabled": True,
                    "mfa": "enforced",
                    "groups": ["All Staff", "Finance"],
                },
                {
                    "upn": "pat@lab.example",
                    "display_name": "Pat Ng",
                    "department": "Warehouse",
                    "title": "Picker",
                    "enabled": True,
                    "mfa": "enforced",
                    "groups": ["All Staff", "Warehouse"],
                },
            ],
        }
    )


def test_happy_path_three_actions() -> None:
    rows = parse_people(Path("examples/people.csv").read_text(encoding="utf-8"))
    summary = build_plan(rows, _lab(), source="people.csv", now=NOW)
    assert summary.ok
    by_upn = {change.upn: change for change in summary.changes}
    assert "create enabled account" in by_upn["alex@lab.example"].steps
    assert "add group Operations" in by_upn["sam@lab.example"].steps
    assert "remove group Finance" in by_upn["sam@lab.example"].steps
    assert "disable account" in by_upn["pat@lab.example"].steps
    assert "add group Disabled Users" in by_upn["pat@lab.example"].steps


def test_joiner_already_exists() -> None:
    rows = parse_people(
        "action,upn,display_name,groups\njoiner,sam@lab.example,Sam Ortiz,All Staff\n"
    )
    summary = build_plan(rows, _lab(), source="x", now=NOW)
    assert not summary.ok
    assert "already exists" in summary.changes[0].message


def test_unknown_group() -> None:
    rows = parse_people(
        "action,upn,display_name,groups\njoiner,new@lab.example,New Person,Secret Club\n"
    )
    summary = build_plan(rows, _lab(), source="x", now=NOW)
    assert not summary.ok
    assert "unknown group" in summary.changes[0].message


def test_leaver_missing() -> None:
    rows = parse_people("action,upn\nleaver,ghost@lab.example\n")
    summary = build_plan(rows, _lab(), source="x", now=NOW)
    assert not summary.ok
    assert "not in the directory" in summary.changes[0].message


def test_apply_writes_new_users_without_graph() -> None:
    rows = parse_people(Path("examples/people.csv").read_text(encoding="utf-8"))
    summary = apply_plan(rows, _lab(), source="people.csv", now=NOW)
    assert summary.ok
    assert summary.directory is not None
    alex = summary.directory.user("alex@lab.example")
    sam = summary.directory.user("sam@lab.example")
    pat = summary.directory.user("pat@lab.example")
    assert alex is not None and alex.enabled and "Finance" in alex.groups
    assert sam is not None and sam.department == "Operations"
    assert "Finance" not in sam.groups
    assert pat is not None and pat.enabled is False and pat.mfa == "none"
    assert "Disabled Users" in pat.groups
    assert summary.to_dict()["writes_to_graph"] is False
