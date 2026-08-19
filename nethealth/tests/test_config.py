from __future__ import annotations

import os
from pathlib import Path

import pytest

from nethealth.config import ConfigError, load_suite, parse_suite

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_toml_suite() -> None:
    suite = load_suite(FIXTURES / "suite.toml")
    assert suite.name == "fixture-suite"
    assert suite.timeout_seconds == 1.5
    assert suite.warn_tls_days == 21
    assert len(suite.checks) == 2
    assert suite.checks[0].type == "icmp"
    assert suite.checks[1].params["expect"] == ["127.0.0.1"]


def test_load_json_suite() -> None:
    suite = load_suite(FIXTURES / "suite.json")
    assert suite.name == "json-suite"
    assert suite.checks[0].type == "http"
    assert suite.checks[0].params["expect_status"] == 200


def test_load_example_lab_suite() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "lab.toml"
    suite = load_suite(example)
    assert suite.name == "lab"
    assert {check.type for check in suite.checks} <= {"icmp", "dns", "tcp", "http", "tls"}


def test_unknown_type() -> None:
    with pytest.raises(ConfigError, match="unknown type"):
        parse_suite({"name": "x", "checks": [{"name": "a", "type": "snmp"}]})


def test_missing_required_param() -> None:
    with pytest.raises(ConfigError, match="missing 'port'"):
        parse_suite({"name": "x", "checks": [{"name": "ssh", "type": "tcp", "host": "127.0.0.1"}]})


def test_bad_http_url() -> None:
    with pytest.raises(ConfigError, match="url must start"):
        parse_suite({"name": "x", "checks": [{"name": "web", "type": "http", "url": "ftp://x"}]})


def test_empty_checks() -> None:
    with pytest.raises(ConfigError, match="non-empty"):
        parse_suite({"name": "x", "checks": []})


def test_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unsupported suite format"):
        load_suite(path)


def test_malformed_toml_is_config_error(tmp_path: Path) -> None:
    path = tmp_path / "suite.toml"
    path.write_text('name = "x"\nthis is not toml\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_suite(path)


def test_malformed_json_is_config_error(tmp_path: Path) -> None:
    path = tmp_path / "suite.json"
    path.write_text('{"name": "x", ', encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_suite(path)


def test_json_array_rejected(tmp_path: Path) -> None:
    path = tmp_path / "suite.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be an object"):
        load_suite(path)


def test_non_utf8_file_is_config_error(tmp_path: Path) -> None:
    path = tmp_path / "suite.toml"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match="not valid UTF-8"):
        load_suite(path)


def test_unreadable_file_is_config_error(tmp_path: Path) -> None:
    path = tmp_path / "suite.toml"
    path.write_text('name = "x"\n', encoding="utf-8")
    path.chmod(0o000)
    try:
        if os.access(path, os.R_OK):  # running as root, permissions do not apply
            pytest.skip("cannot make a file unreadable as this user")
        with pytest.raises(ConfigError, match="cannot read"):
            load_suite(path)
    finally:
        path.chmod(0o644)


def test_duplicate_check_names_rejected() -> None:
    with pytest.raises(ConfigError, match="duplicate check name"):
        parse_suite(
            {
                "name": "x",
                "checks": [
                    {"name": "dup", "type": "dns", "query": "localhost"},
                    {"name": "dup", "type": "dns", "query": "localhost"},
                ],
            }
        )


@pytest.mark.parametrize(
    "check",
    [
        {"name": "a", "type": "tcp", "host": "127.0.0.1", "port": True},
        {"name": "a", "type": "tls", "host": "example.invalid", "port": True},
    ],
)
def test_boolean_port_rejected(check: dict) -> None:
    with pytest.raises(ConfigError, match="port must be an integer"):
        parse_suite({"name": "x", "checks": [check]})


def test_boolean_warn_tls_days_rejected() -> None:
    with pytest.raises(ConfigError, match="warn_tls_days"):
        parse_suite(
            {
                "name": "x",
                "warn_tls_days": True,
                "checks": [{"name": "a", "type": "dns", "query": "localhost"}],
            }
        )


def test_boolean_timeout_rejected() -> None:
    with pytest.raises(ConfigError, match="timeout_seconds"):
        parse_suite(
            {
                "name": "x",
                "timeout_seconds": True,
                "checks": [{"name": "a", "type": "dns", "query": "localhost"}],
            }
        )


def test_boolean_expect_status_rejected() -> None:
    with pytest.raises(ConfigError, match="expect_status"):
        parse_suite(
            {
                "name": "x",
                "checks": [
                    {"name": "a", "type": "http", "url": "http://x.invalid", "expect_status": True}
                ],
            }
        )


def test_boolean_warn_days_rejected() -> None:
    with pytest.raises(ConfigError, match="warn_days"):
        parse_suite(
            {
                "name": "x",
                "checks": [
                    {"name": "a", "type": "tls", "host": "x.invalid", "warn_days": True}
                ],
            }
        )


@pytest.mark.parametrize("host", ["", "   ", "with space"])
def test_bad_host_rejected(host: str) -> None:
    with pytest.raises(ConfigError, match="host must"):
        parse_suite({"name": "x", "checks": [{"name": "a", "type": "icmp", "host": host}]})


def test_empty_dns_query_rejected() -> None:
    with pytest.raises(ConfigError, match="query must"):
        parse_suite({"name": "x", "checks": [{"name": "a", "type": "dns", "query": ""}]})


def test_host_is_trimmed() -> None:
    suite = parse_suite(
        {"name": "x", "checks": [{"name": "a", "type": "icmp", "host": "  127.0.0.1  "}]}
    )
    assert suite.checks[0].params["host"] == "127.0.0.1"


@pytest.mark.parametrize("expect", ["127.0.0.1", [], [1, 2], ["ok", ""]])
def test_bad_dns_expect_rejected(expect: object) -> None:
    with pytest.raises(ConfigError, match="expect must"):
        parse_suite(
            {
                "name": "x",
                "checks": [
                    {"name": "a", "type": "dns", "query": "localhost", "expect": expect}
                ],
            }
        )
