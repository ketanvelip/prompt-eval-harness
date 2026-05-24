"""Project-level configuration (eval.config.yaml + env vars)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


_DEFAULT_CONFIG_PATH = Path("eval.config.yaml")


class ThresholdConfig(BaseModel):
    case_pass: float = 0.75
    suite_pass_rate: float = 0.90
    regression: float = 0.05
    improvement: float = 0.05


class JudgeConfig(BaseModel):
    model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    weight: float = 0.70


class AssertionConfig(BaseModel):
    weight: float = 0.30


class EvalConfig(BaseModel):
    thresholds: ThresholdConfig = ThresholdConfig()
    judge: JudgeConfig = JudgeConfig()
    assertions: AssertionConfig = AssertionConfig()
    suites_dir: str = "suites"
    results_dir: str = ".eval-results"


_cached: Optional[EvalConfig] = None


def load_config(path: Path = _DEFAULT_CONFIG_PATH) -> EvalConfig:
    global _cached
    if _cached is not None:
        return _cached

    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _cached = EvalConfig.model_validate(raw)
    else:
        _cached = EvalConfig()

    return _cached


def get_together_api_key() -> str:
    key = os.environ.get("TOGETHER_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "TOGETHER_API_KEY environment variable is not set.\n"
            "Export it before running:  export TOGETHER_API_KEY=<your-key>"
        )
    return key
