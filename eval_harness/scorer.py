"""Assertion-based scoring (Phase 1) and LLM-judge scoring (Phase 2)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .models import Assertion, AssertionResult

if TYPE_CHECKING:
    pass


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
# LLM-as-Judge  (Phase 2 — stub for now)
# ---------------------------------------------------------------------------

async def score_with_judge(
    output: str,
    rubric: str,
    input_vars: dict,
    *,
    client,
    model: str,
) -> tuple[float, str]:
    """
    Ask an LLM to rate output quality against the rubric.

    Returns (score 0-1, reason string).
    Stub returns (1.0, "judge not yet enabled") until Phase 2 is wired in.
    """
    # Phase 2 implementation will go here.
    # For now, return a neutral score so Phase 1 tests can run.
    return 1.0, "judge not yet enabled (Phase 2)"
