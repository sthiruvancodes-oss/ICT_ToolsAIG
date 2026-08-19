from __future__ import annotations

import html
import json
from datetime import timezone

from nethealth.models import CheckResult, RunSummary

_STATUS_ORDER = ("pass", "fail", "error", "skip")


def render(summary: RunSummary, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(summary.to_dict(), indent=2) + "\n"
    if fmt == "html":
        return render_html(summary)
    if fmt == "text":
        return render_text(summary)
    raise ValueError(f"unsupported format: {fmt}")


def render_text(summary: RunSummary) -> str:
    started = summary.started_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = summary.counts
    lines = [
        f"nethealth  {summary.name}  {started}",
        "",
    ]
    name_w = max((len(r.name) for r in summary.results), default=4)
    type_w = max((len(r.check_type) for r in summary.results), default=4)
    target_w = max((len(r.target) for r in summary.results), default=6)
    for result in summary.results:
        latency = f"{result.latency_ms:.1f}ms" if result.latency_ms is not None else "-"
        lines.append(
            f"{result.status.upper():<5}  "
            f"{result.name:<{name_w}}  "
            f"{result.check_type:<{type_w}}  "
            f"{result.target:<{target_w}}  "
            f"{latency:>8}  "
            f"{result.message}"
        )
    lines.append("")
    parts = [f"{counts[key]} {key}" for key in _STATUS_ORDER if counts[key]]
    outcome = "OK" if summary.ok else "FAILED"
    lines.append(f"{outcome}  {', '.join(parts) or 'no checks'}  ({summary.duration_ms:.1f}ms)")
    lines.append("")
    return "\n".join(lines)


def render_html(summary: RunSummary) -> str:
    started = html.escape(summary.started_at.astimezone(timezone.utc).isoformat())
    counts = summary.counts
    rows = "\n".join(_html_row(result) for result in summary.results)
    outcome = "OK" if summary.ok else "FAILED"
    outcome_class = "ok" if summary.ok else "failed"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>nethealth — {html.escape(summary.name)}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 32px; color: #1a1a1a; }}
    h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 4px; }}
    .meta {{ color: #555; margin-bottom: 20px; }}
    .outcome {{ font-weight: 600; }}
    .outcome.ok {{ color: #0b6b3a; }}
    .outcome.failed {{ color: #a12622; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #ddd; font-size: 14px; }}
    th {{ color: #555; font-weight: 600; }}
    td.status {{ font-variant: small-caps; font-weight: 600; }}
    tr.pass td.status {{ color: #0b6b3a; }}
    tr.fail td.status, tr.error td.status {{ color: #a12622; }}
    tr.skip td.status {{ color: #6b5a00; }}
    .counts {{ margin-top: 16px; color: #555; }}
  </style>
</head>
<body>
  <h1>nethealth — {html.escape(summary.name)}</h1>
  <p class="meta">{started} · <span class="outcome {outcome_class}">{outcome}</span></p>
  <table>
    <thead>
      <tr><th>Status</th><th>Name</th><th>Type</th><th>Target</th><th>Latency</th><th>Message</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p class="counts">{counts['pass']} pass · {counts['fail']} fail · {counts['error']} error · {counts['skip']} skip · {summary.duration_ms:.1f}ms</p>
</body>
</html>
"""


def _html_row(result: CheckResult) -> str:
    latency = f"{result.latency_ms:.1f}ms" if result.latency_ms is not None else "—"
    return (
        f'      <tr class="{html.escape(result.status)}">'
        f'<td class="status">{html.escape(result.status)}</td>'
        f"<td>{html.escape(result.name)}</td>"
        f"<td>{html.escape(result.check_type)}</td>"
        f"<td>{html.escape(result.target)}</td>"
        f"<td>{html.escape(latency)}</td>"
        f"<td>{html.escape(result.message)}</td>"
        f"</tr>"
    )
