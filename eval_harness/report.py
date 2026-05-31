"""Generate a self-contained HTML report from one or more RunRecords."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

from .models import RunRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    if score >= 0.75:
        return "#22c55e"   # green
    if score >= 0.50:
        return "#eab308"   # yellow
    return "#ef4444"       # red


def _bar(score: float, width: int = 80) -> str:
    filled = round(score * width)
    color = _score_color(score)
    return (
        '<div style="background:#e5e7eb;border-radius:4px;height:10px;width:{}px">'
        '<div style="background:{};border-radius:4px;height:10px;width:{}px"></div>'
        "</div>"
    ).format(width, color, filled)


def _icon(passed: bool) -> str:
    return '<span style="color:#22c55e">✓</span>' if passed else '<span style="color:#ef4444">✗</span>'


# ---------------------------------------------------------------------------
# Per-record section
# ---------------------------------------------------------------------------

def _record_section(record: RunRecord) -> str:
    ts = record.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    suite_color = "#22c55e" if record.suite_passed else "#ef4444"
    suite_label = "PASSED" if record.suite_passed else "FAILED"

    rows = []
    for c in record.cases:
        assertion_failures = " · ".join(
            r.message for r in c.assertion_results if not r.passed and r.message
        )
        judge_cell = ""
        if c.judge_score is not None:
            judge_cell = (
                '<td style="color:{}">{:.2f}</td>'
                '<td style="font-size:0.8em;color:#6b7280;max-width:260px">{}</td>'
            ).format(_score_color(c.judge_score), c.judge_score, c.judge_reason or "")
        else:
            judge_cell = "<td>—</td><td></td>"

        rows.append(
            "<tr>"
            "<td><code>{}</code></td>"
            "<td>{} <span style='color:{}'>{:.2f}</span></td>"
            "<td>{}</td>"
            "<td style='font-size:0.8em;color:#6b7280'>{}</td>"
            "{}"
            "<td style='color:#9ca3af'>{:.0f} ms</td>"
            "</tr>"
        ).format(
            c.case_id,
            _bar(c.final_score),
            _score_color(c.final_score),
            c.final_score,
            _icon(c.passed),
            assertion_failures or "",
            judge_cell,
            c.latency_ms,
        )

    has_judge = any(c.judge_score is not None for c in record.cases)
    judge_headers = "<th>Judge</th><th>Judge reason</th>" if has_judge else ""

    return """
<section style="margin-bottom:2.5rem;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
  <div style="background:#f9fafb;padding:1rem 1.25rem;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:baseline">
    <div>
      <span style="font-weight:700;font-size:1.1em">{suite}</span>
      <span style="color:#6b7280;margin-left:1rem;font-size:0.9em">{run_id}</span>
      <span style="color:#9ca3af;margin-left:0.75rem;font-size:0.85em">{ts}</span>
    </div>
    <div>
      <span style="color:#6b7280;font-size:0.9em">{model}</span>
      &nbsp;
      <span style="font-weight:700;color:{suite_color}">{suite_label}</span>
      <span style="color:#6b7280;margin-left:0.5rem">avg {avg:.3f} · {pct:.0f}% pass</span>
    </div>
  </div>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:0.9em">
      <thead style="background:#f3f4f6">
        <tr>
          <th style="text-align:left;padding:0.5rem 0.75rem">Case</th>
          <th style="text-align:left;padding:0.5rem 0.75rem">Score</th>
          <th style="padding:0.5rem 0.75rem">Pass</th>
          <th style="text-align:left;padding:0.5rem 0.75rem">Failures</th>
          {judge_headers}
          <th style="text-align:right;padding:0.5rem 0.75rem">Latency</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</section>
""".format(
        suite=record.suite,
        run_id=record.run_id,
        ts=ts,
        model="{}:{}".format(record.provider, record.model),
        suite_color=suite_color,
        suite_label=suite_label,
        avg=record.avg_score,
        pct=record.pass_rate * 100,
        judge_headers=judge_headers,
        rows="\n        ".join(rows),
    )


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------

def render_html(records: list[RunRecord], title: str = "Eval Report") -> str:
    sections = "\n".join(_record_section(r) for r in records)
    overall_pass = all(r.suite_passed for r in records)
    banner_color = "#22c55e" if overall_pass else "#ef4444"
    banner_text = "All suites passed" if overall_pass else "One or more suites failed"
    n_suites = len(records)
    n_cases = sum(len(r.cases) for r in records)

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 0; padding: 2rem; background: #fff; color: #111; max-width: 1100px; margin: 0 auto; }}
    table td, table th {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }}
    table tr:last-child td {{ border-bottom: none; }}
    code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 0.85em; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p style="color:#6b7280;margin-top:0;margin-bottom:1.5rem">
    {n_suites} suite(s) · {n_cases} case(s) &nbsp;
    <span style="font-weight:700;color:{banner_color}">{banner_text}</span>
  </p>
  {sections}
</body>
</html>""".format(
        title=title,
        n_suites=n_suites,
        n_cases=n_cases,
        banner_color=banner_color,
        banner_text=banner_text,
        sections=sections,
    )


def write_report(records: list[RunRecord], path: Path, title: str = "Eval Report") -> None:
    path.write_text(render_html(records, title=title), encoding="utf-8")
