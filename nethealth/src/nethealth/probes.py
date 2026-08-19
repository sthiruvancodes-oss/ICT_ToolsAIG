from __future__ import annotations

import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from nethealth.models import CheckResult, CheckSpec

ProbeFn = Callable[[CheckSpec, float, int], CheckResult]

_PING_RTT = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


def run_probe(spec: CheckSpec, timeout: float, warn_tls_days: int) -> CheckResult:
    probe = PROBES.get(spec.type)
    if probe is None:
        return CheckResult(
            name=spec.name,
            check_type=spec.type,
            target="",
            status="error",
            message=f"unknown check type {spec.type!r}",
        )
    try:
        return probe(spec, timeout, warn_tls_days)
    except Exception as exc:  # noqa: BLE001 — surface unexpected probe failures as check errors
        return CheckResult(
            name=spec.name,
            check_type=spec.type,
            target=_target(spec),
            status="error",
            message=f"{type(exc).__name__}: {exc}",
        )


def probe_icmp(spec: CheckSpec, timeout: float, _warn_tls_days: int) -> CheckResult:
    host = str(spec.params["host"])
    ping = shutil.which("ping")
    if ping is None:
        return CheckResult(
            name=spec.name,
            check_type="icmp",
            target=host,
            status="skip",
            message="ping binary not found on PATH",
        )

    command = _ping_command(ping, host, timeout)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 1,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name=spec.name,
            check_type="icmp",
            target=host,
            status="fail",
            message=f"ping timed out after {timeout}s",
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    rtt = _parse_ping_rtt(completed.stdout)
    latency = rtt if rtt is not None else (time.perf_counter() - started) * 1000
    if completed.returncode == 0:
        return CheckResult(
            name=spec.name,
            check_type="icmp",
            target=host,
            status="pass",
            message="echo reply received",
            latency_ms=latency,
        )
    detail = (completed.stderr or completed.stdout).strip().splitlines()
    hint = detail[-1] if detail else f"exit {completed.returncode}"
    return CheckResult(
        name=spec.name,
        check_type="icmp",
        target=host,
        status="fail",
        message=hint,
        latency_ms=latency,
        details={"returncode": completed.returncode},
    )


def probe_tcp(spec: CheckSpec, timeout: float, _warn_tls_days: int) -> CheckResult:
    host = str(spec.params["host"])
    port = int(spec.params["port"])
    target = f"{host}:{port}"
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return CheckResult(
            name=spec.name,
            check_type="tcp",
            target=target,
            status="fail",
            message=str(exc),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    return CheckResult(
        name=spec.name,
        check_type="tcp",
        target=target,
        status="pass",
        message="connection established",
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def probe_dns(spec: CheckSpec, timeout: float, _warn_tls_days: int) -> CheckResult:
    query = str(spec.params["query"])
    record = str(spec.params.get("record", "A"))
    family = socket.AF_INET if record == "A" else socket.AF_INET6
    target = f"{query} {record}"
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(query, None, family, socket.SOCK_STREAM)
    except OSError as exc:
        return CheckResult(
            name=spec.name,
            check_type="dns",
            target=target,
            status="fail",
            message=str(exc),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    addresses = sorted({info[4][0] for info in infos})
    latency = (time.perf_counter() - started) * 1000
    expected = spec.params.get("expect")
    if expected is not None:
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            return CheckResult(
                name=spec.name,
                check_type="dns",
                target=target,
                status="error",
                message="expect must be a list of address strings",
                latency_ms=latency,
            )
        missing = [item for item in expected if item not in addresses]
        if missing:
            return CheckResult(
                name=spec.name,
                check_type="dns",
                target=target,
                status="fail",
                message=f"missing addresses: {', '.join(missing)}",
                latency_ms=latency,
                details={"addresses": addresses},
            )
    return CheckResult(
        name=spec.name,
        check_type="dns",
        target=target,
        status="pass",
        message=", ".join(addresses) if addresses else "resolved",
        latency_ms=latency,
        details={"addresses": addresses},
    )


def probe_http(spec: CheckSpec, timeout: float, _warn_tls_days: int) -> CheckResult:
    url = str(spec.params["url"])
    expect_status = int(spec.params.get("expect_status", 200))
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "nethealth/0.1"},
    )
    started = time.perf_counter()
    status: int | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.getcode())
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
    except urllib.error.URLError as exc:
        reason = exc.reason if exc.reason else exc
        message = _tls_hint(reason) if isinstance(reason, ssl.SSLError) else str(reason)
        return CheckResult(
            name=spec.name,
            check_type="http",
            target=url,
            status="fail",
            message=message,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    latency = (time.perf_counter() - started) * 1000
    if status == expect_status:
        return CheckResult(
            name=spec.name,
            check_type="http",
            target=url,
            status="pass",
            message=f"HTTP {status}",
            latency_ms=latency,
            details={"status": status},
        )
    return CheckResult(
        name=spec.name,
        check_type="http",
        target=url,
        status="fail",
        message=f"HTTP {status}, expected {expect_status}",
        latency_ms=latency,
        details={"status": status, "expect_status": expect_status},
    )


def probe_tls(spec: CheckSpec, timeout: float, warn_tls_days: int) -> CheckResult:
    host = str(spec.params["host"])
    port = int(spec.params.get("port", 443))
    warn_days = int(spec.params.get("warn_days", warn_tls_days))
    target = f"{host}:{port}"
    context = ssl.create_default_context()
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                cert = tls_sock.getpeercert()
    except OSError as exc:
        return CheckResult(
            name=spec.name,
            check_type="tls",
            target=target,
            status="fail",
            message=_tls_hint(exc),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    latency = (time.perf_counter() - started) * 1000
    if not cert or "notAfter" not in cert:
        return CheckResult(
            name=spec.name,
            check_type="tls",
            target=target,
            status="fail",
            message="peer certificate missing notAfter",
            latency_ms=latency,
        )

    expires = datetime.fromtimestamp(
        ssl.cert_time_to_seconds(cert["notAfter"]),
        tz=timezone.utc,
    )
    now = datetime.now(timezone.utc)
    days_left = (expires - now).days
    details: dict[str, Any] = {
        "not_after": expires.isoformat(),
        "days_left": days_left,
        "subject": _cert_name(cert.get("subject")),
    }
    if days_left < 0:
        return CheckResult(
            name=spec.name,
            check_type="tls",
            target=target,
            status="fail",
            message=f"certificate expired {-days_left} day(s) ago",
            latency_ms=latency,
            details=details,
        )
    if days_left <= warn_days:
        return CheckResult(
            name=spec.name,
            check_type="tls",
            target=target,
            status="fail",
            message=f"certificate expires in {days_left} day(s) (threshold {warn_days})",
            latency_ms=latency,
            details=details,
        )
    return CheckResult(
        name=spec.name,
        check_type="tls",
        target=target,
        status="pass",
        message=f"certificate valid, {days_left} day(s) remaining",
        latency_ms=latency,
        details=details,
    )


def _tls_hint(exc: BaseException) -> str:
    """Certificate verification failures are usually a missing local trust store, not a bad peer."""
    message = str(exc)
    if isinstance(exc, ssl.SSLCertVerificationError) and _trust_store_missing():
        message += (
            " — this Python has no CA trust store, so every HTTPS check will fail."
            " On a python.org macOS build run 'Install Certificates.command';"
            " elsewhere set SSL_CERT_FILE to a CA bundle."
        )
    return message


def _trust_store_missing() -> bool:
    paths = ssl.get_default_verify_paths()
    cafile = paths.cafile or paths.openssl_cafile
    capath = paths.capath or paths.openssl_capath
    has_file = bool(cafile) and os.path.isfile(cafile)
    has_dir = bool(capath) and os.path.isdir(capath)
    return not (has_file or has_dir)


def _ping_command(ping: str, host: str, timeout: float) -> list[str]:
    if sys.platform == "darwin":
        wait_ms = max(1, int(timeout * 1000))
        return [ping, "-c", "1", "-W", str(wait_ms), host]
    if sys.platform.startswith("win"):
        wait_ms = max(1, int(timeout * 1000))
        return [ping, "-n", "1", "-w", str(wait_ms), host]
    wait_s = max(1, int(timeout))
    return [ping, "-c", "1", "-W", str(wait_s), host]


def _parse_ping_rtt(output: str) -> float | None:
    match = _PING_RTT.search(output)
    if not match:
        return None
    return float(match.group(1))


def _cert_name(subject: Any) -> str | None:
    if not subject:
        return None
    for relative in subject:
        for key, value in relative:
            if key == "commonName":
                return str(value)
    return None


def _target(spec: CheckSpec) -> str:
    params = spec.params
    if spec.type == "tcp":
        return f"{params.get('host')}:{params.get('port')}"
    if spec.type == "dns":
        return f"{params.get('query')} {params.get('record', 'A')}"
    if spec.type == "http":
        return str(params.get("url", ""))
    if spec.type == "tls":
        return f"{params.get('host')}:{params.get('port', 443)}"
    return str(params.get("host", ""))


PROBES: dict[str, ProbeFn] = {
    "icmp": probe_icmp,
    "tcp": probe_tcp,
    "dns": probe_dns,
    "http": probe_http,
    "tls": probe_tls,
}
