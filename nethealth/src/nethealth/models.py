from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Status = Literal["pass", "fail", "error", "skip"]

EXIT_OK = 0
EXIT_CHECKS_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


@dataclass(frozen=True)
class CheckSpec:
    name: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SuiteConfig:
    name: str
    timeout_seconds: float
    warn_tls_days: int
    checks: tuple[CheckSpec, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    check_type: str
    target: str
    status: Status
    message: str
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.check_type,
            "target": self.target,
            "status": self.status,
            "message": self.message,
            "latency_ms": round(self.latency_ms, 3) if self.latency_ms is not None else None,
            "details": self.details,
        }


@dataclass(frozen=True)
class RunSummary:
    name: str
    started_at: datetime
    duration_ms: float
    results: tuple[CheckResult, ...]

    @property
    def counts(self) -> dict[str, int]:
        tallies = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
        for result in self.results:
            tallies[result.status] += 1
        return tallies

    @property
    def ok(self) -> bool:
        return self.counts["fail"] == 0 and self.counts["error"] == 0

    def to_dict(self) -> dict[str, Any]:
        counts = self.counts
        return {
            "name": self.name,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "duration_ms": round(self.duration_ms, 3),
            "ok": self.ok,
            "summary": {**counts, "total": len(self.results)},
            "results": [result.to_dict() for result in self.results],
        }
