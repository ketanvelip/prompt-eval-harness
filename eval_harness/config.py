"""Project-level configuration (eval.config.yaml + env vars)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, Field


_DEFAULT_CONFIG_PATH = Path("eval.config.yaml")


class ThresholdConfig(BaseModel):
    case_pass: float = 0.75
    suite_pass_rate: float = 0.90
    regression: float = 0.05
    improvement: float = 0.05


class JudgeConfig(BaseModel):
    model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    provider: str = "together"
    weight: float = 0.70


class AssertionConfig(BaseModel):
    weight: float = 0.30


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = ""


_DEFAULT_PROVIDERS: Dict[str, ProviderConfig] = {
    "together": ProviderConfig(
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
    ),
    "openai": ProviderConfig(
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "groq": ProviderConfig(
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
    ),
    "ollama": ProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key_env="",
    ),
}


class EvalConfig(BaseModel):
    thresholds: ThresholdConfig = ThresholdConfig()
    judge: JudgeConfig = JudgeConfig()
    assertions: AssertionConfig = AssertionConfig()
    suites_dir: str = "suites"
    results_dir: str = ".eval-results"
    providers: Dict[str, ProviderConfig] = Field(
        default_factory=lambda: dict(_DEFAULT_PROVIDERS)
    )


class SuiteConfig(BaseModel):
    name: str = ""
    description: str = ""


_cached: Optional[EvalConfig] = None


def load_suite_config(suite_dir: Path, global_config: EvalConfig) -> tuple[SuiteConfig, ThresholdConfig]:
    """Load suite.yaml if present and return merged thresholds."""
    path = suite_dir / "suite.yaml"
    if not path.exists():
        return SuiteConfig(), global_config.thresholds
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    suite_cfg = SuiteConfig(name=raw.get("name", ""), description=raw.get("description", ""))
    overrides = raw.get("thresholds", {})
    if overrides:
        merged = global_config.thresholds.model_dump()
        merged.update(overrides)
        return suite_cfg, ThresholdConfig(**merged)
    return suite_cfg, global_config.thresholds


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


def get_api_key(provider: str, config: EvalConfig) -> str:
    """Resolve the API key for a provider, raising a clear error if missing."""
    provider_cfg = config.providers.get(provider)
    if provider_cfg is None:
        raise ValueError(
            "Unknown provider '{}'. Add it under 'providers:' in eval.config.yaml.".format(provider)
        )
    if not provider_cfg.api_key_env:
        return "no-key"  # providers like Ollama need no auth
    key = os.environ.get(provider_cfg.api_key_env, "")
    if not key:
        raise EnvironmentError(
            "{} is not set (required for provider '{}').".format(
                provider_cfg.api_key_env, provider
            )
        )
    return key
