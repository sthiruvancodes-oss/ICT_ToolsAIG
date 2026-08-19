from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from nethealth.models import CheckSpec
from nethealth.probes import (
    _parse_ping_rtt,
    _tls_hint,
    probe_dns,
    probe_http,
    probe_icmp,
    probe_tcp,
    probe_tls,
    run_probe,
)


def _spec(check_type: str, **params: object) -> CheckSpec:
    return CheckSpec(name="t", type=check_type, params=params)


def test_tcp_pass() -> None:
    with patch("nethealth.probes.socket.create_connection") as conn:
        conn.return_value.__enter__.return_value = MagicMock()
        result = probe_tcp(_spec("tcp", host="127.0.0.1", port=22), timeout=1, _warn_tls_days=14)
    assert result.status == "pass"
    assert result.target == "127.0.0.1:22"


def test_tcp_fail() -> None:
    with patch("nethealth.probes.socket.create_connection", side_effect=ConnectionRefusedError("refused")):
        result = probe_tcp(_spec("tcp", host="127.0.0.1", port=9), timeout=1, _warn_tls_days=14)
    assert result.status == "fail"
    assert "refused" in result.message.lower() or result.message


def test_dns_pass_with_expect() -> None:
    info = (None, None, None, None, ("127.0.0.1", 0))
    with patch("nethealth.probes.socket.getaddrinfo", return_value=[info]):
        result = probe_dns(
            _spec("dns", query="localhost", record="A", expect=["127.0.0.1"]),
            timeout=1,
            _warn_tls_days=14,
        )
    assert result.status == "pass"
    assert result.details["addresses"] == ["127.0.0.1"]


def test_dns_missing_expected() -> None:
    info = (None, None, None, None, ("::1", 0))
    with patch("nethealth.probes.socket.getaddrinfo", return_value=[info]):
        result = probe_dns(
            _spec("dns", query="localhost", record="A", expect=["127.0.0.1"]),
            timeout=1,
            _warn_tls_days=14,
        )
    assert result.status == "fail"
    assert "127.0.0.1" in result.message


def test_http_status_mismatch() -> None:
    error = __import__("urllib.error").error.HTTPError(
        url="http://127.0.0.1/x",
        code=404,
        msg="not found",
        hdrs=None,
        fp=None,
    )
    with patch("nethealth.probes.urllib.request.urlopen", side_effect=error):
        result = probe_http(
            _spec("http", url="http://127.0.0.1/x", expect_status=200),
            timeout=1,
            _warn_tls_days=14,
        )
    assert result.status == "fail"
    assert result.details["status"] == 404


def test_http_pass() -> None:
    response = MagicMock()
    response.getcode.return_value = 200
    response.__enter__.return_value = response
    with patch("nethealth.probes.urllib.request.urlopen", return_value=response):
        result = probe_http(
            _spec("http", url="http://127.0.0.1/", expect_status=200),
            timeout=1,
            _warn_tls_days=14,
        )
    assert result.status == "pass"


def test_icmp_skip_without_ping() -> None:
    with patch("nethealth.probes.shutil.which", return_value=None):
        result = probe_icmp(_spec("icmp", host="127.0.0.1"), timeout=1, _warn_tls_days=14)
    assert result.status == "skip"


def test_icmp_pass_parses_rtt() -> None:
    completed = MagicMock(returncode=0, stdout="64 bytes from 127.0.0.1: icmp_seq=0 time=0.412 ms\n", stderr="")
    with patch("nethealth.probes.shutil.which", return_value="/sbin/ping"):
        with patch("nethealth.probes.subprocess.run", return_value=completed):
            result = probe_icmp(_spec("icmp", host="127.0.0.1"), timeout=1, _warn_tls_days=14)
    assert result.status == "pass"
    assert result.latency_ms == pytest.approx(0.412)


def test_tls_valid_certificate() -> None:
    cert = {
        "notAfter": "Dec 31 23:59:59 2099 GMT",
        "subject": ((("commonName", "localhost"),),),
    }
    tls_sock = MagicMock()
    tls_sock.getpeercert.return_value = cert
    tls_sock.__enter__.return_value = tls_sock
    raw_sock = MagicMock()
    raw_sock.__enter__.return_value = raw_sock
    context = MagicMock()
    context.wrap_socket.return_value = tls_sock
    with patch("nethealth.probes.socket.create_connection", return_value=raw_sock):
        with patch("nethealth.probes.ssl.create_default_context", return_value=context):
            result = probe_tls(_spec("tls", host="localhost", port=443), timeout=1, warn_tls_days=14)
    assert result.status == "pass"
    assert result.details["days_left"] >= 89


def test_tls_expiring_fails_threshold() -> None:
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    not_after = soon.strftime("%b %d %H:%M:%S %Y GMT")
    cert = {"notAfter": not_after, "subject": ((("commonName", "localhost"),),)}
    tls_sock = MagicMock()
    tls_sock.getpeercert.return_value = cert
    tls_sock.__enter__.return_value = tls_sock
    raw_sock = MagicMock()
    raw_sock.__enter__.return_value = raw_sock
    context = MagicMock()
    context.wrap_socket.return_value = tls_sock
    with patch("nethealth.probes.socket.create_connection", return_value=raw_sock):
        with patch("nethealth.probes.ssl.create_default_context", return_value=context):
            result = probe_tls(_spec("tls", host="localhost", port=443, warn_days=14), timeout=1, warn_tls_days=14)
    assert result.status == "fail"
    assert "threshold" in result.message


def test_unknown_type_is_error() -> None:
    result = run_probe(_spec("snmp"), timeout=1, warn_tls_days=14)
    assert result.status == "error"


def test_parse_ping_rtt_keeps_zero() -> None:
    assert _parse_ping_rtt("64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.0 ms") == 0.0
    assert _parse_ping_rtt("no timing here") is None


def test_icmp_zero_rtt_is_not_replaced_by_wall_clock() -> None:
    completed = MagicMock(returncode=0, stdout="time=0.0 ms", stderr="")
    with patch("nethealth.probes.shutil.which", return_value="/sbin/ping"):
        with patch("nethealth.probes.subprocess.run", return_value=completed):
            result = probe_icmp(_spec("icmp", host="127.0.0.1"), timeout=1, _warn_tls_days=14)
    assert result.status == "pass"
    assert result.latency_ms == 0.0


def test_tls_hint_added_when_trust_store_missing() -> None:
    exc = ssl.SSLCertVerificationError("certificate verify failed")
    with patch("nethealth.probes._trust_store_missing", return_value=True):
        assert "no CA trust store" in _tls_hint(exc)


def test_tls_hint_absent_when_trust_store_present() -> None:
    exc = ssl.SSLCertVerificationError("certificate verify failed")
    with patch("nethealth.probes._trust_store_missing", return_value=False):
        assert "no CA trust store" not in _tls_hint(exc)


def test_tls_hint_leaves_ordinary_errors_alone() -> None:
    assert _tls_hint(ConnectionRefusedError("refused")) == "refused"
