from __future__ import annotations

from datetime import datetime, timezone

from idops.models import (
    Change,
    Directory,
    MfaState,
    PersonRow,
    PlanSummary,
    User,
)

DISABLED_GROUP = "Disabled Users"


def build_plan(
    rows: tuple[PersonRow, ...],
    directory: Directory,
    *,
    source: str,
    now: datetime | None = None,
) -> PlanSummary:
    started = now or datetime.now(timezone.utc)
    working = {user.upn.casefold(): user for user in directory.users}
    changes: list[Change] = []
    for row in rows:
        change, updated = _plan_row(row, directory, working)
        changes.append(change)
        if change.status == "ok" and updated is not None:
            working[updated.upn.casefold()] = updated
    return PlanSummary(
        tenant=directory.tenant,
        source=source,
        started_at=started,
        changes=tuple(changes),
    )


def apply_plan(
    rows: tuple[PersonRow, ...],
    directory: Directory,
    *,
    source: str,
    now: datetime | None = None,
) -> PlanSummary:
    plan = build_plan(rows, directory, source=source, now=now)
    if not plan.ok:
        return plan
    users = {user.upn.casefold(): user for user in directory.users}
    for row in rows:
        _, updated = _plan_row(row, directory, users)
        if updated is None:
            continue
        users[updated.upn.casefold()] = updated
    ordered = tuple(sorted(users.values(), key=lambda user: user.upn.casefold()))
    return PlanSummary(
        tenant=directory.tenant,
        source=source,
        started_at=plan.started_at,
        changes=plan.changes,
        directory=Directory(tenant=directory.tenant, groups=directory.groups, users=ordered),
    )


def _plan_row(
    row: PersonRow,
    directory: Directory,
    working: dict[str, User],
) -> tuple[Change, User | None]:
    if row.action == "joiner":
        return _plan_joiner(row, directory, working)
    if row.action == "mover":
        return _plan_mover(row, directory, working)
    return _plan_leaver(row, directory, working)


def _plan_joiner(
    row: PersonRow,
    directory: Directory,
    working: dict[str, User],
) -> tuple[Change, User | None]:
    if row.upn.casefold() in working:
        return _error(row, f"{row.upn} already exists"), None
    groups, group_error = _resolve_groups(row.groups, directory)
    if group_error:
        return _error(row, group_error), None
    if not groups:
        return _error(row, "joiner needs at least one group"), None
    if not row.display_name:
        return _error(row, "joiner needs display_name"), None
    mfa: MfaState = "enforced" if row.mfa_required is not False else "disabled"
    steps = [
        "create enabled account",
        *[f"add group {name}" for name in groups],
        f"set MFA {mfa}",
    ]
    user = User(
        upn=row.upn,
        display_name=row.display_name,
        department=row.department,
        title=row.title,
        enabled=True,
        mfa=mfa,
        groups=groups,
    )
    return _ok(row, steps, "would create the account in the lab directory"), user


def _plan_mover(
    row: PersonRow,
    directory: Directory,
    working: dict[str, User],
) -> tuple[Change, User | None]:
    current = working.get(row.upn.casefold())
    if current is None:
        return _error(row, f"{row.upn} is not in the directory"), None
    if not current.enabled:
        return _error(row, f"{row.upn} is disabled; rehire as a joiner"), None
    groups, group_error = _resolve_groups(row.groups, directory)
    if group_error:
        return _error(row, group_error), None
    target_groups = groups if groups else current.groups
    if not target_groups:
        return _error(row, "mover would leave the account with no groups"), None
    add = [name for name in target_groups if name not in current.groups]
    remove = [name for name in current.groups if name not in target_groups]
    display_name = row.display_name or current.display_name
    department = row.department or current.department
    title = row.title or current.title
    mfa = current.mfa
    if row.mfa_required is True:
        mfa = "enforced"
    elif row.mfa_required is False:
        mfa = "disabled"
    steps: list[str] = []
    if display_name != current.display_name:
        steps.append(f"set display name to {display_name}")
    if department != current.department:
        steps.append(f"set department to {department or '(blank)'}")
    if title != current.title:
        steps.append(f"set title to {title or '(blank)'}")
    steps.extend(f"remove group {name}" for name in remove)
    steps.extend(f"add group {name}" for name in add)
    if mfa != current.mfa:
        steps.append(f"set MFA {mfa}")
    if not steps:
        steps.append("no directory changes")
    user = User(
        upn=current.upn,
        display_name=display_name,
        department=department,
        title=title,
        enabled=True,
        mfa=mfa,
        groups=target_groups,
    )
    return _ok(row, steps, "would update the account in the lab directory"), user


def _plan_leaver(
    row: PersonRow,
    directory: Directory,
    working: dict[str, User],
) -> tuple[Change, User | None]:
    current = working.get(row.upn.casefold())
    if current is None:
        return _error(row, f"{row.upn} is not in the directory"), None
    if not current.enabled:
        return _error(row, f"{row.upn} is already disabled"), None
    steps = ["disable account", "note: revoke sessions in the real tenant, not here"]
    remaining: list[str] = []
    disabled = directory.canonical_group(DISABLED_GROUP)
    for name in current.groups:
        if disabled and name.casefold() == disabled.casefold():
            remaining.append(disabled)
            continue
        steps.append(f"remove group {name}")
    if disabled and disabled not in remaining:
        remaining.append(disabled)
        steps.append(f"add group {disabled}")
    if current.mfa != "none":
        steps.append("set MFA none")
    user = User(
        upn=current.upn,
        display_name=current.display_name,
        department=current.department,
        title=current.title,
        enabled=False,
        mfa="none",
        groups=tuple(remaining),
    )
    return _ok(row, steps, "would disable the account in the lab directory"), user


def _resolve_groups(names: tuple[str, ...], directory: Directory) -> tuple[tuple[str, ...], str | None]:
    resolved: list[str] = []
    missing: list[str] = []
    for name in names:
        canonical = directory.canonical_group(name)
        if canonical is None:
            missing.append(name)
        else:
            resolved.append(canonical)
    if missing:
        return (), f"unknown group(s): {', '.join(missing)}"
    return tuple(resolved), None


def _ok(row: PersonRow, steps: list[str], message: str) -> Change:
    return Change(
        upn=row.upn,
        action=row.action,
        status="ok",
        steps=tuple(steps),
        message=message,
        line=row.line,
    )


def _error(row: PersonRow, message: str) -> Change:
    return Change(
        upn=row.upn,
        action=row.action,
        status="error",
        steps=(),
        message=message,
        line=row.line,
    )
