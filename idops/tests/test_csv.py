from __future__ import annotations

from pathlib import Path

import pytest

from idops.csv_load import parse_people
from idops.errors import ConfigError


def test_duplicate_upn() -> None:
    with pytest.raises(ConfigError, match="duplicate upn"):
        parse_people(
            "action,upn,display_name,groups\n"
            "joiner,a@lab.example,A,All Staff\n"
            "leaver,a@lab.example,A,\n"
        )


def test_bad_action() -> None:
    with pytest.raises(ConfigError, match="action must be"):
        parse_people("action,upn\nrehire,a@lab.example\n")


def test_missing_column() -> None:
    with pytest.raises(ConfigError, match="missing required"):
        parse_people("upn\na@lab.example\n")


def test_unknown_column() -> None:
    with pytest.raises(ConfigError, match="unknown column"):
        parse_people("action,upn,password\njoiner,a@lab.example,secret\n")


def test_example_csv_loads() -> None:
    rows = parse_people(Path("examples/people.csv").read_text(encoding="utf-8"))
    assert [row.action for row in rows] == ["joiner", "mover", "leaver"]
