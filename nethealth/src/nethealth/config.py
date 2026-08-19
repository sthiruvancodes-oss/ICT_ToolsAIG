from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from nethealth.models import CheckSpec, SuiteConfig

KNOWN_TYPES = frozenset({"icmp", "tcp", "dns", "http", "tls"})
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "icmp": ("host",),
    "tcp": ("host", "port"),
    "dns": ("query",),
    "http": ("url",),
    "tls": ("host",),
}


class ConfigError(ValueError):
    """Invalid suite file or CLI check definition."""


def load_suite(path: Path) -> SuiteConfig:
    suffix = path.suffix.lower()
    if suffix not in {".toml", ".json"}:
        raise ConfigError(f"unsupported suite format: {path.suffix or '(none)'} (use .toml or .json)")

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path}: not valid UTF-8 text ({exc.reason})") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc

    if suffix == ".toml":
        try:
            data: Any = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path}: invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: JSON suite must be an object")
    return parse_suite(data)


def parse_suite(data: dict[str, Any]) -> SuiteConfig:
    name = data.get("name", "unnamed")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("suite 'name' must be a non-empty string")

    timeout = data.get("timeout_seconds", 3.0)
    if not _is_number(timeout) or timeout <= 0:
        raise ConfigError("timeout_seconds must be a positive number")

    warn_tls_days = data.get("warn_tls_days", 14)
    if not _is_int(warn_tls_days) or warn_tls_days < 0:
        raise ConfigError("warn_tls_days must be a non-negative integer")

    checks_raw = data.get("checks")
    if not isinstance(checks_raw, list) or not checks_raw:
        raise ConfigError("suite must define a non-empty 'checks' list")

    checks = tuple(_parse_check(item, index) for index, item in enumerate(checks_raw, start=1))
    reject_duplicate_names(checks)
    return SuiteConfig(
        name=name.strip(),
        timeout_seconds=float(timeout),
        warn_tls_days=warn_tls_days,
        checks=checks,
    )


def _parse_check(item: Any, index: int) -> CheckSpec:
    if not isinstance(item, dict):
        raise ConfigError(f"check {index} must be a table/object")

    name = item.get("name")
    check_type = item.get("type")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"check {index} needs a non-empty 'name'")
    if not isinstance(check_type, str) or check_type not in KNOWN_TYPES:
        known = ", ".join(sorted(KNOWN_TYPES))
        raise ConfigError(f"check {index} ({name!r}) has unknown type {check_type!r}; expected one of: {known}")

    params = {key: value for key, value in item.items() if key not in {"name", "type"}}
    for required in REQUIRED_PARAMS[check_type]:
        if required not in params:
            raise ConfigError(f"check {name!r} ({check_type}) is missing '{required}'")

    if check_type in {"icmp", "tcp", "tls"}:
        params["host"] = _require_hostname(name, params["host"])
    if check_type == "tcp":
        _require_port(name, params["port"])
    if check_type == "tls" and "port" in params:
        _require_port(name, params["port"])
    if check_type == "dns":
        params["query"] = _require_hostname(name, params["query"], field="query")
        record = params.get("record", "A")
        if record not in {"A", "AAAA"}:
            raise ConfigError(f"check {name!r} dns record must be A or AAAA")
        params["record"] = record
        expect = params.get("expect")
        if expect is not None:
            if not isinstance(expect, list) or not expect:
                raise ConfigError(f"check {name!r} expect must be a non-empty list of addresses")
            if not all(isinstance(item, str) and item.strip() for item in expect):
                raise ConfigError(f"check {name!r} expect must contain only address strings")
            params["expect"] = [item.strip() for item in expect]
    if check_type == "http":
        url = params["url"]
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ConfigError(f"check {name!r} url must start with http:// or https://")
        status = params.get("expect_status", 200)
        if not _is_int(status) or not (100 <= status <= 599):
            raise ConfigError(f"check {name!r} expect_status must be an HTTP status code")
        params["expect_status"] = status
    if check_type == "tls":
        params.setdefault("port", 443)
        warn_days = params.get("warn_days")
        if warn_days is not None and (not _is_int(warn_days) or warn_days < 0):
            raise ConfigError(f"check {name!r} warn_days must be a non-negative integer")

    return CheckSpec(name=name.strip(), type=check_type, params=params)


def _require_port(name: str, port: Any) -> None:
    if not _is_int(port) or not (1 <= port <= 65535):
        raise ConfigError(f"check {name!r} port must be an integer 1-65535")


def _require_hostname(name: str, value: Any, field: str = "host") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"check {name!r} {field} must be a non-empty string")
    host = value.strip()
    if any(char.isspace() for char in host):
        raise ConfigError(f"check {name!r} {field} must not contain whitespace")
    return host


def reject_duplicate_names(checks: tuple[CheckSpec, ...]) -> None:
    """Names key the report rows, so ambiguous duplicates are rejected up front."""
    seen: set[str] = set()
    for spec in checks:
        if spec.name in seen:
            raise ConfigError(f"duplicate check name {spec.name!r}; names must be unique")
        seen.add(spec.name)


def _is_int(value: Any) -> bool:
    # bool is a subclass of int, so `port = true` would otherwise parse as port 1.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
