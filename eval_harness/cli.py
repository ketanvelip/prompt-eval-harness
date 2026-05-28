"""CLI entry point for eval-harness."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from .config import load_config
from .runner import run_suite
from .storage import list_runs, load_run, save_run

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    if score >= 0.75:
        return "green"
    if score >= 0.50:
        return "yellow"
    return "red"


def _passed_icon(passed: bool) -> str:
    return "✓" if passed else "✗"


def _print_run(record, config):
    """Pretty-print a RunRecord to the terminal."""
    console.rule(f"[bold]Run: {record.run_id}[/bold]")
    console.print(
        f"  Suite: [cyan]{record.suite}[/cyan]  "
        f"Prompt: [cyan]{record.prompt_name}[/cyan]  "
        f"Model: [cyan]{record.model}[/cyan]"
    )
    console.print()

    # Per-case table
    tbl = Table(box=box.SIMPLE_HEAD, show_footer=False)
    tbl.add_column("Case", style="bold")
    tbl.add_column("Score", justify="right")
    tbl.add_column("Pass?", justify="center")
    tbl.add_column("Latency", justify="right")
    tbl.add_column("Failures")

    has_judge = any(c.judge_score is not None for c in record.cases)
    if has_judge:
        tbl.add_column("Judge", justify="right")
        tbl.add_column("Judge reason")

    for case in record.cases:
        color = _score_color(case.final_score)
        failures = "; ".join(
            r.message for r in case.assertion_results if not r.passed and r.message
        )
        row = [
            case.case_id,
            Text(f"{case.final_score:.2f}", style=color),
            Text(_passed_icon(case.passed), style="green" if case.passed else "red"),
            f"{case.latency_ms:.0f} ms",
            failures or "—",
        ]
        if has_judge:
            j = case.judge_score
            row.append(Text(f"{j:.2f}" if j is not None else "—", style=_score_color(j) if j is not None else "dim"))
            row.append(case.judge_reason or "—")
        tbl.add_row(*row)

    console.print(tbl)

    # Summary
    suite_color = "green" if record.suite_passed else "red"
    console.print(
        f"  Avg score: [{_score_color(record.avg_score)}]{record.avg_score:.3f}[/]  "
        f"Pass rate: [{suite_color}]{record.pass_rate*100:.0f}%[/]  "
        f"Suite: [{suite_color}]{'PASSED' if record.suite_passed else 'FAILED'}[/]"
    )
    console.print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Prompt Eval Harness — run, compare, and track prompt quality."""
    pass


@cli.command()
@click.argument("suite")
@click.option("--prompt", "prompt_file", default=None, help="Path to a specific prompt.yaml")
@click.option("--no-judge", "skip_judge", is_flag=True, default=False, help="Skip LLM judge; use assertions only")
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def run(suite: str, prompt_file: str | None, skip_judge: bool, config_path: str):
    """Run all test cases in SUITE against the suite's prompt."""
    cfg = load_config(Path(config_path))

    def progress(i: int, total: int, case_id: str):
        console.print(f"  [{i+1}/{total}] Running [cyan]{case_id}[/cyan] …", end="\r")

    try:
        record = run_suite(
            suite, cfg,
            prompt_file=prompt_file,
            use_judge=not skip_judge,
            progress_callback=progress,
        )
    except Exception as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise SystemExit(1)

    console.print()  # clear progress line
    out_path = save_run(record, cfg.results_dir)
    console.print(f"  Saved → [dim]{out_path}[/dim]\n")
    _print_run(record, cfg)

    raise SystemExit(0 if record.suite_passed else 1)


@cli.command()
@click.argument("run_id_a")
@click.argument("run_id_b")
@click.option("--suite", default=None, help="Suite name (required if run IDs are ambiguous)")
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def compare(run_id_a: str, run_id_b: str, suite: str | None, config_path: str):
    """Diff two result files side by side."""
    cfg = load_config(Path(config_path))
    results_dir = cfg.results_dir

    def find_run(run_id: str) -> Path:
        # Search all suites if suite not specified
        search_root = Path(results_dir)
        if suite:
            candidates = list((search_root / suite).glob(f"{run_id}.json"))
        else:
            candidates = list(search_root.rglob(f"{run_id}.json"))
        if not candidates:
            raise FileNotFoundError(f"No result file found for run ID: {run_id}")
        return candidates[0]

    try:
        path_a = find_run(run_id_a)
        path_b = find_run(run_id_b)
        rec_a = load_run(path_a)
        rec_b = load_run(path_b)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)

    console.rule("[bold]Compare[/bold]")
    console.print(
        f"  [dim]A[/dim] {rec_a.run_id}  prompt={rec_a.prompt_name}  "
        f"avg={rec_a.avg_score:.3f}  pass={rec_a.pass_rate*100:.0f}%"
    )
    console.print(
        f"  [dim]B[/dim] {rec_b.run_id}  prompt={rec_b.prompt_name}  "
        f"avg={rec_b.avg_score:.3f}  pass={rec_b.pass_rate*100:.0f}%"
    )

    delta = rec_b.avg_score - rec_a.avg_score
    threshold = cfg.thresholds
    if delta > threshold.improvement:
        verdict = f"[green]IMPROVEMENT[/green] (+{delta:.3f})"
    elif delta < -threshold.regression:
        verdict = f"[red]REGRESSION[/red] ({delta:.3f})"
    else:
        verdict = f"[yellow]NEUTRAL[/yellow] ({delta:+.3f})"
    console.print(f"\n  Verdict: {verdict}\n")

    # Per-case diff table
    cases_a = {c.case_id: c for c in rec_a.cases}
    cases_b = {c.case_id: c for c in rec_b.cases}
    all_ids = sorted(set(cases_a) | set(cases_b))

    tbl = Table(box=box.SIMPLE_HEAD)
    tbl.add_column("Case")
    tbl.add_column("Score A", justify="right")
    tbl.add_column("Score B", justify="right")
    tbl.add_column("Δ", justify="right")

    for cid in all_ids:
        sa = cases_a[cid].final_score if cid in cases_a else None
        sb = cases_b[cid].final_score if cid in cases_b else None
        if sa is not None and sb is not None:
            d = sb - sa
            color = "green" if d > 0.01 else ("red" if d < -0.01 else "white")
            tbl.add_row(cid, f"{sa:.2f}", f"{sb:.2f}", Text(f"{d:+.2f}", style=color))
        elif sa is None:
            tbl.add_row(cid, "—", f"{sb:.2f}", Text("new", style="green"))
        else:
            tbl.add_row(cid, f"{sa:.2f}", "—", Text("removed", style="dim"))

    console.print(tbl)


@cli.command()
@click.argument("suite")
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def history(suite: str, config_path: str):
    """Show score trend for SUITE over all saved runs."""
    cfg = load_config(Path(config_path))
    paths = list_runs(suite, cfg.results_dir)

    if not paths:
        console.print(f"[yellow]No results found for suite '{suite}'.[/yellow]")
        raise SystemExit(0)

    tbl = Table(box=box.SIMPLE_HEAD, title=f"History — {suite}")
    tbl.add_column("Run ID")
    tbl.add_column("Timestamp")
    tbl.add_column("Prompt")
    tbl.add_column("Model")
    tbl.add_column("Avg Score", justify="right")
    tbl.add_column("Pass Rate", justify="right")
    tbl.add_column("Suite", justify="center")

    prev_avg = None
    for p in paths:
        rec = load_run(p)
        trend = ""
        if prev_avg is not None:
            d = rec.avg_score - prev_avg
            if d > 0.01:
                trend = " ▲"
            elif d < -0.01:
                trend = " ▼"
        prev_avg = rec.avg_score

        suite_color = "green" if rec.suite_passed else "red"
        avg_color = _score_color(rec.avg_score)
        tbl.add_row(
            rec.run_id,
            rec.timestamp.strftime("%Y-%m-%d %H:%M"),
            rec.prompt_name,
            rec.model,
            Text(f"{rec.avg_score:.3f}{trend}", style=avg_color),
            f"{rec.pass_rate*100:.0f}%",
            Text("PASS" if rec.suite_passed else "FAIL", style=suite_color),
        )

    console.print(tbl)


if __name__ == "__main__":
    cli()
