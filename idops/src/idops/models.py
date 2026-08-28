from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Action = Literal["joiner", "mover", "leaver"]
MfaState = Literal["enforced", "disabled", "none"]
RowStatus = Literal["ok", "error"]

EXIT_OK = 0
EXIT_PLAN_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

REQUIRED_CSV_COLUMNS = ("action", "upn")
OPTIONAL_CSV_COLUMNS = (
    "display_name",
    "department",
    "title",
    "groups",
    "mfa_required",
)


@dataclass(frozen=True)
class PersonRow:
    action: Action
    upn: str
    display_name: str
    department: str
    title: str
    groups: tuple[str, ...]
    mfa_required: bool | None
    line: int


@dataclass(frozen=True)
class User:
    upn: str
    display_name: str
    department: str
    title: str
    enabled: bool
    mfa: MfaState
    groups: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "upn": self.upn,
            "display_name": self.display_name,
            "department": self.department,
            "title": self.title,
            "enabled": self.enabled,
            "mfa": self.mfa,
            "groups": list(self.groups),
        }


@dataclass(frozen=True)
class Directory:
    tenant: str
    groups: tuple[str, ...]
    users: tuple[User, ...]

    def user(self, upn: str) -> User | None:
        key = upn.casefold()
        for user in self.users:
            if user.upn.casefold() == key:
                return user
        return None

    def has_group(self, name: str) -> bool:
        key = name.casefold()
        return any(group.casefold() == key for group in self.groups)

    def canonical_group(self, name: str) -> str | None:
        key = name.casefold()
        for group in self.groups:
            if group.casefold() == key:
                return group
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant,
            "groups": list(self.groups),
            "users": [user.to_dict() for user in self.users],
        }


@dataclass(frozen=True)
class Change:
    upn: str
    action: Action
    status: RowStatus
    steps: tuple[str, ...]
    message: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "upn": self.upn,
            "action": self.action,
            "status": self.status,
            "steps": list(self.steps),
            "message": self.message,
            "line": self.line,
        }


@dataclass(frozen=True)
class PlanSummary:
    tenant: str
    source: str
    started_at: datetime
    changes: tuple[Change, ...]
    directory: Directory | None = field(default=None)

    @property
    def ok(self) -> bool:
        return all(change.status == "ok" for change in self.changes) and bool(self.changes)

    @property
    def counts(self) -> dict[str, int]:
        tallies = {"ok": 0, "error": 0, "joiner": 0, "mover": 0, "leaver": 0}
        for change in self.changes:
            tallies[change.status] += 1
            tallies[change.action] += 1
        return tallies

    def to_dict(self) -> dict[str, Any]:
        counts = self.counts
        payload: dict[str, Any] = {
            "tenant": self.tenant,
            "source": self.source,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "ok": self.ok,
            "lab_only": True,
            "writes_to_graph": False,
            "summary": {**counts, "total": len(self.changes)},
            "changes": [change.to_dict() for change in self.changes],
        }
        if self.directory is not None:
            payload["directory"] = self.directory.to_dict()
        return payload
