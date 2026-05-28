"""CLI entry point for eval-harness."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

import yaml

from .config import load_config
from .runner import parse_model_arg, run_suite
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
@click.option("--model", default=None, help="Override model: 'model-id' or 'provider:model-id'")
@click.option("--no-judge", "skip_judge", is_flag=True, default=False, help="Skip LLM judge; use assertions only")
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def run(suite: str, prompt_file: str | None, model: str | None, skip_judge: bool, config_path: str):
    """Run all test cases in SUITE against the suite's prompt."""
    cfg = load_config(Path(config_path))

    provider_override = None
    model_override = None
    if model:
        provider_override, model_override = parse_model_arg(model)

    def progress(i: int, total: int, case_id: str):
        console.print(f"  [{i+1}/{total}] Running [cyan]{case_id}[/cyan] …", end="\r")

    try:
        record = run_suite(
            suite, cfg,
            prompt_file=prompt_file,
            model_override=model_override,
            provider_override=provider_override,
            use_judge=not skip_judge,
            progress_callback=progress,
        )
    except Exception as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise SystemExit(1)

    console.print()
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


def _short_model(model_id: str, max_len: int = 22) -> str:
    name = model_id.split("/")[-1] if "/" in model_id else model_id
    return name if len(name) <= max_len else name[:max_len - 1] + "…"


@cli.command("compare-models")
@click.argument("suite")
@click.option("--model", "models", multiple=True, required=True,
              help="Model to compare: 'model-id' or 'provider:model-id'. Repeat for each model.")
@click.option("--prompt", "prompt_file", default=None, help="Path to a specific prompt.yaml")
@click.option("--no-judge", "skip_judge", is_flag=True, default=False)
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def compare_models(
    suite: str,
    models: tuple[str, ...],
    prompt_file: str | None,
    skip_judge: bool,
    config_path: str,
):
    """Run SUITE against multiple models and show a side-by-side comparison."""
    cfg = load_config(Path(config_path))
    records = []

    for idx, model_arg in enumerate(models):
        provider_override, model_override = parse_model_arg(model_arg)
        label = f"[{idx+1}/{len(models)}] {provider_override}:{model_override}"
        console.print(f"\n  Running {label} …")

        def progress(i: int, total: int, case_id: str, _label=label):
            console.print(f"    [{i+1}/{total}] [cyan]{case_id}[/cyan] …", end="\r")

        try:
            record = run_suite(
                suite, cfg,
                prompt_file=prompt_file,
                model_override=model_override,
                provider_override=provider_override,
                use_judge=not skip_judge,
                progress_callback=progress,
            )
        except Exception as exc:
            console.print(f"\n  [red]Error running {model_arg}:[/red] {exc}")
            raise SystemExit(1)

        console.print()
        save_run(record, cfg.results_dir)
        records.append(record)

    # Build comparison table
    console.print()
    console.rule(f"[bold]Model Comparison — {suite}[/bold]")

    headers = [_short_model(r.model) for r in records]

    tbl = Table(box=box.SIMPLE_HEAD)
    tbl.add_column("Case", style="bold")
    for h in headers:
        tbl.add_column(h, justify="center")

    all_case_ids = [c.case_id for c in records[0].cases]
    case_maps = [{c.case_id: c for c in r.cases} for r in records]

    for cid in all_case_ids:
        row = [cid]
        for cm in case_maps:
            c = cm.get(cid)
            if c is None:
                row.append("—")
            else:
                color = _score_color(c.final_score)
                icon = _passed_icon(c.passed)
                row.append(Text(f"{c.final_score:.2f} {icon}", style=color))
        tbl.add_row(*row)

    # Summary rows
    tbl.add_section()
    avg_row = ["Avg Score"]
    pass_row = ["Pass Rate"]
    suite_row = ["Suite"]
    for r in records:
        avg_row.append(Text(f"{r.avg_score:.3f}", style=_score_color(r.avg_score)))
        suite_color = "green" if r.suite_passed else "red"
        pass_row.append(f"{r.pass_rate*100:.0f}%")
        suite_row.append(Text("PASS" if r.suite_passed else "FAIL", style=suite_color))
    tbl.add_row(*avg_row)
    tbl.add_row(*pass_row)
    tbl.add_row(*suite_row)

    console.print(tbl)


_ASSERTION_TYPES = [
    "not_empty", "max_length", "min_length", "contains", "not_contains",
    "starts_with", "ends_with", "is_json", "regex",
]
_VALUED_ASSERTIONS = {"max_length", "min_length", "contains", "not_contains", "starts_with", "ends_with", "regex"}


@cli.command("add-case")
@click.argument("suite")
@click.option("--config", "config_path", default="eval.config.yaml", show_default=True)
def add_case(suite: str, config_path: str):
    """Interactively add a new test case to SUITE."""
    cfg = load_config(Path(config_path))
    suite_dir = Path(cfg.suites_dir) / suite
    cases_dir = suite_dir / "cases"

    if not suite_dir.exists():
        console.print(f"[red]Suite '{suite}' not found at {suite_dir}[/red]")
        raise SystemExit(1)
    cases_dir.mkdir(exist_ok=True)

    console.rule(f"[bold]Add case → {suite}[/bold]")

    # Case ID
    case_id = click.prompt("Case ID (e.g. my-test-case)").strip()
    if not case_id:
        console.print("[red]Case ID cannot be empty.[/red]")
        raise SystemExit(1)
    out_path = cases_dir / f"{case_id}.yaml"
    if out_path.exists() and not click.confirm(f"'{case_id}' already exists. Overwrite?"):
        raise SystemExit(0)

    # Input variables
    inputs: dict = {}
    console.print("\nInput variables [dim](blank name to finish)[/dim]")
    while True:
        key = click.prompt("  Name", default="", show_default=False).strip()
        if not key:
            break
        val = click.prompt(f"  {key}")
        inputs[key] = val
    if not inputs:
        console.print("[yellow]No inputs added — prompt {{variables}} won't be substituted.[/yellow]")

    # Assertions
    assertions: list = []
    console.print(
        "\nAssertions [dim](types: {})[/dim]".format(", ".join(_ASSERTION_TYPES))
    )
    console.print("[dim]Blank type to finish.[/dim]")
    while True:
        a_type = click.prompt("  Type", default="", show_default=False).strip()
        if not a_type:
            break
        if a_type not in _ASSERTION_TYPES:
            console.print(f"  [yellow]Unknown type '{a_type}' — skipped.[/yellow]")
            continue
        if a_type in _VALUED_ASSERTIONS:
            val = click.prompt("    Value").strip()
            if a_type in {"max_length", "min_length"}:
                try:
                    val = int(val)
                except ValueError:
                    pass
            assertions.append({"type": a_type, "value": val})
        else:
            assertions.append({"type": a_type})

    # Rubric
    console.print("\nRubric [dim](what a good output looks like — used by LLM judge; blank to skip)[/dim]")
    rubric = click.prompt("  Rubric", default="", show_default=False).strip()

    # Write YAML
    data: dict = {"id": case_id, "input": inputs}
    if assertions:
        data["assertions"] = assertions
    if rubric:
        data["rubric"] = rubric

    out_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"\n  Written → [dim]{out_path}[/dim]")
    console.print(f"  Run it:   [cyan]eval-harness run {suite}[/cyan]\n")


if __name__ == "__main__":
    cli()
