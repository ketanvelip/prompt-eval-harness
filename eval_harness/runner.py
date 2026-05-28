"""Core eval runner — loads a suite, calls the model provider, scores outputs."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openai import OpenAI

from .config import EvalConfig, get_api_key, load_suite_config
from .models import CaseResult, PromptTemplate, RunRecord, TestCase
from .scorer import score_assertions, score_with_judge


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
        raise FileNotFoundError("No .yaml test cases found in {}".format(cases_dir))
    return cases


def _make_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return "{}_{}".format(ts, short)


def _make_client(provider: str, config: EvalConfig) -> OpenAI:
    provider_cfg = config.providers.get(provider)
    if provider_cfg is None:
        raise ValueError(
            "Unknown provider '{}'. Add it under 'providers:' in eval.config.yaml.".format(provider)
        )
    return OpenAI(
        api_key=get_api_key(provider, config),
        base_url=provider_cfg.base_url,
    )


def parse_model_arg(model_arg: str, default_provider: str = "together") -> tuple[str, str]:
    """
    Parse a model argument into (provider, model_id).

    Accepts 'provider:model-id' or bare 'model-id' (uses default_provider).
    The colon separator is safe because Together.ai model IDs use '/' not ':'.
    """
    if ":" in model_arg:
        provider, model_id = model_arg.split(":", 1)
        return provider.strip(), model_id.strip()
    return default_provider, model_arg.strip()


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_suite(
    suite_name: str,
    config: EvalConfig,
    *,
    prompt_file: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    use_judge: bool = True,
    progress_callback=None,
) -> RunRecord:
    """
    Run a full suite evaluation.

    Args:
        suite_name:       Suite directory name under config.suites_dir.
        config:           Loaded EvalConfig.
        prompt_file:      Override the default prompt.yaml path.
        model_override:   Override the model ID from prompt.yaml.
        provider_override: Override the provider from prompt.yaml.
        use_judge:        If False, skip LLM judge and use assertions only.
        progress_callback: Optional callable(case_index, total, case_id).

    Returns:
        A RunRecord with all results.
    """
    suite_dir = Path(config.suites_dir) / suite_name
    if not suite_dir.is_dir():
        raise FileNotFoundError("Suite directory not found: {}".format(suite_dir))

    prompt_path = Path(prompt_file) if prompt_file else suite_dir / "prompt.yaml"
    if not prompt_path.exists():
        raise FileNotFoundError("Prompt file not found: {}".format(prompt_path))

    _, thresholds = load_suite_config(suite_dir, config)
    prompt = _load_prompt(prompt_path)
    cases = _load_cases(suite_dir / "cases")

    # Apply overrides
    provider = provider_override or prompt.provider
    model = model_override or prompt.model

    client = _make_client(provider, config)
    judge_client = _make_client(config.judge.provider, config)

    case_results: list[CaseResult] = []

    for i, case in enumerate(cases):
        if progress_callback:
            progress_callback(i, len(cases), case.id)

        # Render messages
        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": _render(prompt.system, case.input)})
        messages.append({"role": "user", "content": _render(prompt.user, case.input)})

        # Call the model
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
        )
        latency_ms = (time.monotonic() - t0) * 1000
        output = response.choices[0].message.content or ""

        # Assertion scoring
        assertion_results, assertion_score = score_assertions(output, case.assertions)

        # LLM judge scoring
        judge_score = None
        judge_reason = None
        if use_judge and case.rubric:
            judge_score, judge_reason = score_with_judge(
                output,
                case.rubric,
                case.input,
                client=judge_client,
                model=config.judge.model,
            )

        # Weighted final score
        if judge_score is not None:
            final_score = config.judge.weight * judge_score + config.assertions.weight * assertion_score
        else:
            final_score = assertion_score

        passed = final_score >= thresholds.case_pass

        case_results.append(CaseResult(
            case_id=case.id,
            input=case.input,
            output=output,
            latency_ms=round(latency_ms, 1),
            assertion_results=assertion_results,
            assertion_score=round(assertion_score, 4),
            judge_score=round(judge_score, 4) if judge_score is not None else None,
            judge_reason=judge_reason,
            final_score=round(final_score, 4),
            passed=passed,
        ))

    avg_score = sum(r.final_score for r in case_results) / len(case_results)
    pass_rate = sum(r.passed for r in case_results) / len(case_results)

    return RunRecord(
        run_id=_make_run_id(),
        suite=suite_name,
        prompt_name=prompt.name,
        provider=provider,
        model=model,
        timestamp=datetime.now(timezone.utc),
        cases=case_results,
        avg_score=round(avg_score, 4),
        pass_rate=round(pass_rate, 4),
        suite_passed=pass_rate >= thresholds.suite_pass_rate,
    )
