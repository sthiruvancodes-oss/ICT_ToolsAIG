from __future__ import annotations

import json
from datetime import timezone

from idops.models import Change, PlanSummary


def render(summary: PlanSummary, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(summary.to_dict(), indent=2) + "\n"
    if fmt == "text":
        return render_text(summary)
    raise ValueError(f"unsupported format: {fmt}")


def render_text(summary: PlanSummary) -> str:
    started = summary.started_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = summary.counts
    lines = [
        f"idops  {summary.tenant}  {started}",
        f"source  {summary.source}",
        "lab fixture only; this does not call Graph or Active Directory",
        "",
    ]
    upn_w = max((len(change.upn) for change in summary.changes), default=3)
    action_w = max((len(change.action) for change in summary.changes), default=6)
    for change in summary.changes:
        lines.append(_change_line(change, upn_w, action_w))
        for step in change.steps:
            lines.append(f"         {step}")
    lines.append("")
    outcome = "OK" if summary.ok else "FAILED"
    parts = [
        f"{counts['ok']} ok",
        f"{counts['error']} error",
        f"{counts['joiner']} joiner",
        f"{counts['mover']} mover",
        f"{counts['leaver']} leaver",
    ]
    lines.append(f"{outcome}  {', '.join(parts)}")
    if summary.directory is not None:
        lines.append(f"directory users: {len(summary.directory.users)}")
    lines.append("")
    return "\n".join(lines)


def _change_line(change: Change, upn_w: int, action_w: int) -> str:
    return (
        f"{change.status.upper():<5}  "
        f"{change.action:<{action_w}}  "
        f"{change.upn:<{upn_w}}  "
        f"L{change.line}  "
        f"{change.message}"
    )
