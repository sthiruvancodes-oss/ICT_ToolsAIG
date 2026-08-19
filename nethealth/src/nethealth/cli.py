from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nethealth import __version__
from nethealth.config import ConfigError, load_suite, parse_suite, reject_duplicate_names
from nethealth.models import (
    EXIT_CHECKS_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    CheckSpec,
    SuiteConfig,
)
from nethealth.report import render
from nethealth.runner import run_suite


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"nethealth: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("nethealth: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        # A downstream reader closed the pipe (`nethealth ... | head`). Point stdout at
        # devnull so the interpreter does not report a second error while flushing at exit.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass
        return EXIT_INTERRUPTED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nethealth",
        description=(
            "Run lab-safe ICMP, TCP, DNS, HTTP, and TLS health checks. "
            "Only target hosts and services you operate."
        ),
    )
    parser.add_argument("--version", action="version", version=f"nethealth {__version__}")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="Run health checks from a suite file and/or CLI targets")
    check.add_argument("-c", "--config", type=Path, help="TOML or JSON suite file")
    check.add_argument(
        "--format",
        choices=("text", "json", "html"),
        default="text",
        help="Report format (default: text)",
    )
    check.add_argument("-o", "--output", type=Path, help="Write report to FILE instead of stdout")
    check.add_argument("--jobs", type=int, default=8, help="Concurrent checks (default: 8, 1 = sequential)")
    check.add_argument("--timeout", type=float, help="Override suite timeout in seconds")
    check.add_argument("--icmp", action="append", default=[], metavar="HOST", help="ICMP ping target (repeatable)")
    check.add_argument("--tcp", action="append", default=[], metavar="HOST:PORT", help="TCP connect target (repeatable)")
    check.add_argument("--dns", action="append", default=[], metavar="NAME", help="DNS A lookup (repeatable)")
    check.add_argument("--http", action="append", default=[], metavar="URL", help="HTTP GET target (repeatable)")
    check.add_argument("--tls", action="append", default=[], metavar="HOST[:PORT]", help="TLS certificate check (repeatable)")
    check.set_defaults(func=cmd_check)
    return parser


def cmd_check(args: argparse.Namespace) -> int:
    if args.jobs < 1:
        raise ConfigError("--jobs must be >= 1")
    if args.timeout is not None and args.timeout <= 0:
        raise ConfigError("--timeout must be a positive number")

    suite = _build_suite(args)
    summary = run_suite(suite, jobs=args.jobs)
    body = render(summary, args.format)
    if args.output:
        _write_output(args.output, body)
    else:
        sys.stdout.write(body)
        sys.stdout.flush()
    return EXIT_OK if summary.ok else EXIT_CHECKS_FAILED


def _write_output(path: Path, body: str) -> None:
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot write {path}: {exc.strerror or exc}") from exc


def _build_suite(args: argparse.Namespace) -> SuiteConfig:
    cli_checks = _cli_checks(args)
    if args.config is None and not cli_checks:
        raise ConfigError("provide --config and/or --icmp/--tcp/--dns/--http/--tls")

    if args.config is not None:
        if not args.config.is_file():
            raise ConfigError(f"suite file not found: {args.config}")
        suite = load_suite(args.config)
        checks = suite.checks + cli_checks
        reject_duplicate_names(checks)
        timeout = args.timeout if args.timeout is not None else suite.timeout_seconds
        return SuiteConfig(
            name=suite.name,
            timeout_seconds=timeout,
            warn_tls_days=suite.warn_tls_days,
            checks=checks,
        )

    return parse_suite(
        {
            "name": "cli",
            "timeout_seconds": args.timeout if args.timeout is not None else 3.0,
            "checks": [
                {"name": spec.name, "type": spec.type, **spec.params}
                for spec in cli_checks
            ],
        }
    )


def _cli_checks(args: argparse.Namespace) -> tuple[CheckSpec, ...]:
    raw: list[dict] = []
    for index, host in enumerate(args.icmp, start=1):
        raw.append({"name": f"icmp-{index}", "type": "icmp", "host": host})
    for index, target in enumerate(args.tcp, start=1):
        host, port = _split_host_port(target, default_port=None)
        if port is None:
            raise ConfigError(f"invalid --tcp {target!r}; expected HOST:PORT")
        raw.append({"name": f"tcp-{index}", "type": "tcp", "host": host, "port": port})
    for index, name in enumerate(args.dns, start=1):
        raw.append({"name": f"dns-{index}", "type": "dns", "query": name, "record": "A"})
    for index, url in enumerate(args.http, start=1):
        raw.append({"name": f"http-{index}", "type": "http", "url": url, "expect_status": 200})
    for index, target in enumerate(args.tls, start=1):
        host, port = _split_host_port(target, default_port=443)
        raw.append({"name": f"tls-{index}", "type": "tls", "host": host, "port": port})
    if not raw:
        return ()
    return parse_suite({"name": "cli", "timeout_seconds": 3.0, "checks": raw}).checks


def _split_host_port(value: str, default_port: int | None) -> tuple[str, int | None]:
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            raise ConfigError(f"invalid target {value!r}")
        host = value[1:end]
        rest = value[end + 1 :]
        if rest == "":
            return host, default_port
        if not rest.startswith(":"):
            raise ConfigError(f"invalid target {value!r}")
        return host, _parse_port(rest[1:])
    if ":" not in value:
        return value, default_port
    host, _, port_s = value.rpartition(":")
    if not host:
        raise ConfigError(f"invalid target {value!r}")
    return host, _parse_port(port_s)


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ConfigError(f"invalid port {value!r}") from exc
    if not (1 <= port <= 65535):
        raise ConfigError(f"port out of range: {port}")
    return port
