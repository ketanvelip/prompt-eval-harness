"""Assertion-based scoring and LLM-judge scoring."""

from __future__ import annotations

import json
import re

from .models import Assertion, AssertionResult


# ---------------------------------------------------------------------------
# Assertion checks
# ---------------------------------------------------------------------------

def _check_assertion(output: str, assertion: Assertion) -> AssertionResult:
    t = assertion.type
    v = assertion.value

    if t == "not_empty":
        passed = bool(output.strip())
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else "Output is empty.",
        )

    if t == "max_length":
        passed = len(output) <= int(v)
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Length {len(output)} exceeds max {v}.",
        )

    if t == "min_length":
        passed = len(output) >= int(v)
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Length {len(output)} is below min {v}.",
        )

    if t == "contains":
        passed = str(v) in output
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Output does not contain '{v}'.",
        )

    if t == "not_contains":
        passed = str(v) not in output
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Output contains forbidden string '{v}'.",
        )

    if t == "starts_with":
        passed = output.lstrip().startswith(str(v))
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Output does not start with '{v}'.",
        )

    if t == "ends_with":
        passed = output.rstrip().endswith(str(v))
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Output does not end with '{v}'.",
        )

    if t == "is_json":
        try:
            json.loads(output)
            passed = True
            msg = ""
        except json.JSONDecodeError as exc:
            passed = False
            msg = f"Not valid JSON: {exc}"
        return AssertionResult(assertion_type=t, passed=passed, message=msg)

    if t == "regex":
        match = re.search(str(v), output)
        passed = match is not None
        return AssertionResult(
            assertion_type=t,
            passed=passed,
            message="" if passed else f"Pattern '{v}' not found in output.",
        )

    # Unknown assertion type — fail gracefully
    return AssertionResult(
        assertion_type=t,
        passed=False,
        message=f"Unknown assertion type '{t}'.",
    )


def score_assertions(output: str, assertions: list[Assertion]) -> tuple[list[AssertionResult], float]:
    """
    Run all assertions against an output.

    Returns (results, score) where score is the fraction of assertions passed.
    If there are no assertions, score is 1.0 (no constraints = unconstrained pass).
    """
    if not assertions:
        return [], 1.0

    results = [_check_assertion(output, a) for a in assertions]
    score = sum(r.passed for r in results) / len(results)
    return results, score


# ---------------------------------------------------------------------------
# LLM-as-Judge
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a strict output quality evaluator. "
    "You will be given a rubric describing what a good response looks like, "
    "the input provided to the model, and the model's output. "
    'Respond with a JSON object with exactly two keys: "score" (float 0.0–1.0, '
    "where 1.0 fully meets the rubric and 0.0 completely fails) and "
    '"reason" (one concise sentence explaining your rating). '
    "Output only the JSON object — no markdown, no extra text."
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def _parse_judge_response(text: str) -> tuple[float, str]:
    """Extract (score, reason) from judge response, stripping markdown fences if present."""
    m = _JSON_FENCE_RE.search(text)
    raw = m.group(1) if m else text.strip()
    data = json.loads(raw)
    score = float(data["score"])
    score = max(0.0, min(1.0, score))
    reason = str(data.get("reason", ""))
    return score, reason


def score_with_judge(
    output: str,
    rubric: str,
    input_vars: dict,
    *,
    client,
    model: str,
) -> tuple[float, str]:
    """
    Ask an LLM to rate output quality against the rubric.

    Returns (score 0.0–1.0, reason string).
    Falls back to (0.5, error message) if the judge response cannot be parsed.
    """
    input_summary = "; ".join(
        "{}: {}".format(k, str(v)[:200]) for k, v in input_vars.items()
    )
    user_content = (
        "RUBRIC:\n{}\n\nINPUT:\n{}\n\nMODEL OUTPUT:\n{}".format(
            rubric, input_summary, output
        )
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=128,
        temperature=0.0,
    )

    raw_text = response.choices[0].message.content or ""
    try:
        return _parse_judge_response(raw_text)
    except Exception as exc:
        return 0.5, "judge parse error: {}".format(exc)
