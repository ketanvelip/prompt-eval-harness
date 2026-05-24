"""Core eval runner — loads a suite, calls Together.ai, scores outputs."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openai import OpenAI

from .config import EvalConfig, get_together_api_key
from .models import CaseResult, PromptTemplate, RunRecord, TestCase
from .scorer import score_assertions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _render(template: str, variables: dict) -> str:
    """Replace {{var}} placeholders with values from variables dict."""
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        if key not in variables:
            raise KeyError(
                "Template references '{{{}}}' but test case has no input key '{}'.".format(key, key)
            )
        return str(variables[key])
    return _VAR_RE.sub(replacer, template)


def _load_prompt(path: Path) -> PromptTemplate:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptTemplate.model_validate(raw)


def _load_cases(cases_dir: Path) -> list[TestCase]:
    cases = []
    for f in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        cases.append(TestCase.model_validate(raw))
    if not cases:
        raise FileNotFoundError(f"No .yaml test cases found in {cases_dir}")
    return cases


def _make_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}_{short}"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_suite(
    suite_name: str,
    config: EvalConfig,
    *,
    prompt_file: str | None = None,
    progress_callback=None,
) -> RunRecord:
    """
    Run a full suite evaluation.

    Args:
        suite_name:        Name of the suite directory under config.suites_dir.
        config:            Loaded EvalConfig.
        prompt_file:       Override the default prompt.yaml path.
        progress_callback: Optional callable(case_index, total, case_id) for
                           live progress updates.

    Returns:
        A RunRecord with all results.
    """
    suite_dir = Path(config.suites_dir) / suite_name
    if not suite_dir.is_dir():
        raise FileNotFoundError(f"Suite directory not found: {suite_dir}")

    # Resolve prompt
    if prompt_file:
        prompt_path = Path(prompt_file)
    else:
        prompt_path = suite_dir / "prompt.yaml"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    prompt = _load_prompt(prompt_path)
    cases = _load_cases(suite_dir / "cases")

    # Together.ai client (OpenAI-compatible)
    client = OpenAI(
        api_key=get_together_api_key(),
        base_url="https://api.together.xyz/v1",
    )

    case_results: list[CaseResult] = []

    for i, case in enumerate(cases):
        if progress_callback:
            progress_callback(i, len(cases), case.id)

        # Render prompt
        rendered_user = _render(prompt.user, case.input)
        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": _render(prompt.system, case.input)})
        messages.append({"role": "user", "content": rendered_user})

        # Call Together.ai
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model=prompt.model,
            messages=messages,
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        output = response.choices[0].message.content or ""

        # Score
        assertion_results, assertion_score = score_assertions(output, case.assertions)

        # Phase 1: final score = assertion score only
        final_score = assertion_score
        passed = final_score >= config.thresholds.case_pass

        case_results.append(CaseResult(
            case_id=case.id,
            input=case.input,
            output=output,
            latency_ms=round(latency_ms, 1),
            assertion_results=assertion_results,
            assertion_score=round(assertion_score, 4),
            final_score=round(final_score, 4),
            passed=passed,
        ))

    # Aggregate
    avg_score = sum(r.final_score for r in case_results) / len(case_results)
    pass_rate = sum(r.passed for r in case_results) / len(case_results)
    suite_passed = pass_rate >= config.thresholds.suite_pass_rate

    return RunRecord(
        run_id=_make_run_id(),
        suite=suite_name,
        prompt_name=prompt.name,
        model=prompt.model,
        timestamp=datetime.now(timezone.utc),
        cases=case_results,
        avg_score=round(avg_score, 4),
        pass_rate=round(pass_rate, 4),
        suite_passed=suite_passed,
    )
