from __future__ import annotations

import csv
from pathlib import Path

from idops.errors import ConfigError
from idops.models import OPTIONAL_CSV_COLUMNS, REQUIRED_CSV_COLUMNS, Action, PersonRow

_ACTIONS: frozenset[str] = frozenset({"joiner", "mover", "leaver"})


def load_people(path: Path) -> tuple[PersonRow, ...]:
    if not path.is_file():
        raise ConfigError(f"CSV not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    return parse_people(text)


def parse_people(text: str) -> tuple[PersonRow, ...]:
    reader = csv.DictReader(_strip_blank_lines(text.splitlines()))
    if reader.fieldnames is None:
        raise ConfigError("CSV has no header row")
    columns = [_norm_header(name) for name in reader.fieldnames]
    if any(not name for name in columns):
        raise ConfigError("CSV has an empty header")
    if len(columns) != len(set(columns)):
        raise ConfigError("CSV has duplicate headers")
    missing = [name for name in REQUIRED_CSV_COLUMNS if name not in columns]
    if missing:
        raise ConfigError(f"CSV missing required column(s): {', '.join(missing)}")
    unknown = [
        name
        for name in columns
        if name not in REQUIRED_CSV_COLUMNS and name not in OPTIONAL_CSV_COLUMNS
    ]
    if unknown:
        raise ConfigError(f"CSV has unknown column(s): {', '.join(unknown)}")

    rows: list[PersonRow] = []
    seen: dict[str, int] = {}
    for offset, raw in enumerate(reader, start=2):
        record = {_norm_header(key): (value or "").strip() for key, value in raw.items()}
        if not any(record.values()):
            continue
        upn = record.get("upn", "")
        if not upn:
            raise ConfigError(f"CSV line {offset}: upn is empty")
        key = upn.casefold()
        if key in seen:
            raise ConfigError(f"CSV line {offset}: duplicate upn {upn} (also line {seen[key]})")
        seen[key] = offset
        action = _parse_action(record.get("action", ""), offset)
        rows.append(
            PersonRow(
                action=action,
                upn=upn,
                display_name=record.get("display_name", ""),
                department=record.get("department", ""),
                title=record.get("title", ""),
                groups=_parse_groups(record.get("groups", "")),
                mfa_required=_parse_optional_bool(record.get("mfa_required", ""), offset),
                line=offset,
            )
        )
    if not rows:
        raise ConfigError("CSV has no people rows")
    return tuple(rows)


def _strip_blank_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip()]


def _norm_header(name: str | None) -> str:
    return (name or "").strip().casefold()


def _parse_action(value: str, line: int) -> Action:
    action = value.casefold()
    if action not in _ACTIONS:
        raise ConfigError(f"CSV line {line}: action must be joiner, mover, or leaver")
    return action  # type: ignore[return-value]


def _parse_groups(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [part.strip() for part in value.replace("|", ";").split(";")]
    groups = tuple(part for part in parts if part)
    seen: set[str] = set()
    unique: list[str] = []
    for group in groups:
        key = group.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(group)
    return tuple(unique)


def _parse_optional_bool(value: str, line: int) -> bool | None:
    if value == "":
        return None
    key = value.casefold()
    if key in {"true", "yes", "1", "y"}:
        return True
    if key in {"false", "no", "0", "n"}:
        return False
    raise ConfigError(f"CSV line {line}: mfa_required must be true or false")
