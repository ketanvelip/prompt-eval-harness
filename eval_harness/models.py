"""Data models for the eval harness."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Test case schema (loaded from YAML)
# ---------------------------------------------------------------------------

class Assertion(BaseModel):
    """A single programmatic check on a model output."""
    type: str  # not_empty | max_length | min_length | contains | not_contains
               # starts_with | ends_with | is_json | regex
    value: Any = None  # threshold / expected string / pattern


class TestCase(BaseModel):
    """One test case inside a suite."""
    id: str
    input: dict[str, Any]
    assertions: list[Assertion] = Field(default_factory=list)
    rubric: str = ""  # natural-language quality description (used by LLM judge in Phase 2)


# ---------------------------------------------------------------------------
# Prompt template schema (loaded from YAML)
# ---------------------------------------------------------------------------

class PromptTemplate(BaseModel):
    """A versioned prompt template."""
    name: str
    model: str
    system: str = ""
    user: str  # may contain {{variable}} placeholders
    max_tokens: int = 1024
    temperature: float = 0.0


# ---------------------------------------------------------------------------
# Scoring / result schema
# ---------------------------------------------------------------------------

class AssertionResult(BaseModel):
    assertion_type: str
    passed: bool
    message: str = ""


class CaseResult(BaseModel):
    case_id: str
    input: dict[str, Any]
    output: str
    latency_ms: float
    assertion_results: list[AssertionResult]
    assertion_score: float        # fraction of assertions that passed (0–1)
    judge_score: Optional[float] = None
    judge_reason: Optional[str] = None
    final_score: float            # weighted combination
    passed: bool                  # final_score >= threshold


class RunRecord(BaseModel):
    """Everything produced by a single `eval-harness run` invocation."""
    run_id: str
    suite: str
    prompt_name: str
    model: str
    timestamp: datetime
    cases: list[CaseResult]
    avg_score: float
    pass_rate: float              # fraction of cases that passed
    suite_passed: bool
