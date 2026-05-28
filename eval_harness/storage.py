"""Persist and retrieve RunRecords as JSON files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import RunRecord

_BASELINES_DIR = "baselines"


# ---------------------------------------------------------------------------
# Run results
# ---------------------------------------------------------------------------

def save_run(record: RunRecord, results_dir: str = ".eval-results") -> Path:
    """Save a RunRecord to .eval-results/<suite>/<run_id>.json."""
    out_dir = Path(results_dir) / record.suite
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{record.run_id}.json"
    out_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return out_path


def load_run(path: Path) -> RunRecord:
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def list_runs(suite: str, results_dir: str = ".eval-results") -> list[Path]:
    """Return all result files for a suite, sorted oldest → newest."""
    suite_dir = Path(results_dir) / suite
    if not suite_dir.exists():
        return []
    return sorted(suite_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Baselines  (committed to the repo at baselines/<suite>.json)
# ---------------------------------------------------------------------------

def baseline_path(suite: str, baselines_dir: str = _BASELINES_DIR) -> Path:
    return Path(baselines_dir) / f"{suite}.json"


def save_baseline(record: RunRecord, baselines_dir: str = _BASELINES_DIR) -> Path:
    path = baseline_path(record.suite, baselines_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_baseline(suite: str, baselines_dir: str = _BASELINES_DIR) -> Optional[RunRecord]:
    path = baseline_path(suite, baselines_dir)
    if not path.exists():
        return None
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
