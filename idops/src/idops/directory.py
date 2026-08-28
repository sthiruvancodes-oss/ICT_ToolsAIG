from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from idops.errors import ConfigError
from idops.models import Directory, MfaState, User

_MFA: frozenset[str] = frozenset({"enforced", "disabled", "none"})


def load_directory(path: Path) -> Directory:
    if not path.is_file():
        raise ConfigError(f"directory fixture not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"directory fixture is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("directory fixture must be a JSON object")
    return parse_directory(payload)


def parse_directory(payload: dict[str, Any]) -> Directory:
    tenant = str(payload.get("tenant") or "lab").strip() or "lab"
    groups = _parse_group_catalog(payload.get("groups"))
    raw_users = payload.get("users")
    if not isinstance(raw_users, list):
        raise ConfigError("directory.users must be a list")
    users: list[User] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_users, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"directory.users[{index}] must be an object")
        user = _parse_user(item, groups, index)
        key = user.upn.casefold()
        if key in seen:
            raise ConfigError(f"directory has duplicate upn {user.upn}")
        seen.add(key)
        users.append(user)
    return Directory(tenant=tenant, groups=groups, users=tuple(users))


def dump_directory(directory: Directory) -> str:
    return json.dumps(directory.to_dict(), indent=2) + "\n"


def _parse_group_catalog(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("directory.groups must be a non-empty list of names")
    groups: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item).strip()
        if not name:
            raise ConfigError("directory.groups contains an empty name")
        key = name.casefold()
        if key in seen:
            raise ConfigError(f"directory.groups has duplicate {name}")
        seen.add(key)
        groups.append(name)
    return tuple(groups)


def _parse_user(item: dict[str, Any], groups: tuple[str, ...], index: int) -> User:
    upn = str(item.get("upn") or "").strip()
    if not upn:
        raise ConfigError(f"directory.users[{index}].upn is empty")
    mfa = str(item.get("mfa") or "none").strip().casefold()
    if mfa not in _MFA:
        raise ConfigError(f"directory.users[{index}].mfa must be enforced, disabled, or none")
    membership = item.get("groups", [])
    if not isinstance(membership, list):
        raise ConfigError(f"directory.users[{index}].groups must be a list")
    catalog = {name.casefold(): name for name in groups}
    resolved: list[str] = []
    seen: set[str] = set()
    for name in membership:
        label = str(name).strip()
        key = label.casefold()
        if key not in catalog:
            raise ConfigError(f"directory.users[{index}] references unknown group {label}")
        if key in seen:
            continue
        seen.add(key)
        resolved.append(catalog[key])
    return User(
        upn=upn,
        display_name=str(item.get("display_name") or "").strip(),
        department=str(item.get("department") or "").strip(),
        title=str(item.get("title") or "").strip(),
        enabled=bool(item.get("enabled", True)),
        mfa=mfa,  # type: ignore[arg-type]
        groups=tuple(resolved),
    )
