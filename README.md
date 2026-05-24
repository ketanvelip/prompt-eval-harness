# Prompt Eval Harness

A CLI tool that runs prompts against a defined set of test cases, scores the outputs, and tells you whether a change is an improvement, regression, or neutral — in under 60 seconds.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -e .
export TOGETHER_API_KEY=<your-key>
```

## Usage

### Run a suite
```bash
eval-harness run summarization
```

Runs all test cases in `suites/summarization/cases/` against `suites/summarization/prompt.yaml`.

Use a specific prompt version:
```bash
eval-harness run summarization --prompt suites/summarization/prompt.v2.yaml
```

### Compare two runs
```bash
eval-harness compare 20260524_143022_abc123 20260524_150011_def456
```

### View history
```bash
eval-harness history summarization
```

## Project layout

```
suites/
└── <suite-name>/
    ├── prompt.yaml          # Prompt template ({{variable}} substitution)
    ├── prompt.v2.yaml       # Versioned variants
    └── cases/
        └── *.yaml           # One file per test case

.eval-results/
└── <suite-name>/
    └── <run-id>.json        # Persisted run records

eval.config.yaml             # Configurable thresholds and judge model
```

## Test case format

```yaml
id: my-case
input:
  text: "The text to pass into the prompt"
assertions:
  - type: not_empty
  - type: max_length
    value: 500
  - type: contains
    value: "keyword"
  - type: not_contains
    value: "forbidden"
  - type: is_json
  - type: regex
    value: "\\d{4}"
rubric: >
  Natural language description of what a good output looks like.
  Used by the LLM judge in Phase 2.
```

## Scoring

| Signal | Phase 1 | Phase 2 |
|---|---|---|
| Assertion checks | 100% weight | 30% weight |
| LLM-as-Judge | — | 70% weight |

## Pass/fail thresholds (configurable in eval.config.yaml)

| Condition | Default |
|---|---|
| Case passes | score ≥ 0.75 |
| Suite passes | ≥ 90% of cases pass |
| Regression | avg score drops > 0.05 vs baseline |
| Improvement | avg score rises > 0.05 vs baseline |

## Build phases

- **Phase 1** ✅ Runner + assertion scoring + storage + `run` / `compare` / `history` commands
- **Phase 2** — LLM judge + weighted final score
- **Phase 3** — `add-case` command, starter suites, configurable per-suite thresholds
