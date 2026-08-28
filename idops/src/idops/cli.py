from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from idops import __version__
from idops.csv_load import load_people
from idops.directory import dump_directory, load_directory
from idops.errors import ConfigError
from idops.models import EXIT_INTERRUPTED, EXIT_OK, EXIT_PLAN_FAILED, EXIT_USAGE
from idops.plan import apply_plan, build_plan
from idops.report import render


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"idops: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("idops: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass
        return EXIT_INTERRUPTED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="idops",
        description=(
            "Plan joiner, mover, and leaver changes from a CSV against a lab "
            "directory fixture. It does not call Graph, Entra, or Active Directory."
        ),
    )
    parser.add_argument("--version", action="version", version=f"idops {__version__}")
    sub = parser.add_subparsers(dest="command")

    plan = sub.add_parser("plan", help="Show what would change; write nothing")
    _add_common(plan)
    plan.set_defaults(func=cmd_plan)

    apply = sub.add_parser(
        "apply",
        help="Write an updated lab directory JSON. Still no Graph or AD.",
    )
    _add_common(apply)
    apply.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Updated directory fixture JSON",
    )
    apply.set_defaults(func=cmd_apply)
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-c", "--csv", type=Path, required=True, help="People CSV")
    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        required=True,
        help="Lab directory fixture JSON",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format (default: text)",
    )


def cmd_plan(args: argparse.Namespace) -> int:
    rows = load_people(args.csv)
    directory = load_directory(args.directory)
    summary = build_plan(rows, directory, source=str(args.csv))
    _print_report(summary, args.format)
    return EXIT_OK if summary.ok else EXIT_PLAN_FAILED


def cmd_apply(args: argparse.Namespace) -> int:
    rows = load_people(args.csv)
    directory = load_directory(args.directory)
    summary = apply_plan(rows, directory, source=str(args.csv))
    _print_report(summary, args.format)
    if not summary.ok or summary.directory is None:
        return EXIT_PLAN_FAILED
    _write_output(args.output, dump_directory(summary.directory))
    return EXIT_OK


def _print_report(summary, fmt: str) -> None:
    body = render(summary, fmt)
    sys.stdout.write(body)
    sys.stdout.flush()


def _write_output(path: Path, body: str) -> None:
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot write {path}: {exc.strerror or exc}") from exc
