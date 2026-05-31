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

## Commands

| Command | Description |
|---|---|
| `run SUITE` | Run all cases in a suite |
| `run-ci` | Run all suites with regression checking (CI mode) |
| `compare RUN_A RUN_B` | Diff two result files |
| `compare-models SUITE --model A --model B` | Run suite against multiple models side by side |
| `history SUITE` | Score trend over all saved runs |
| `add-case SUITE` | Interactively add a new test case |
| `baseline set SUITE` | Promote latest run to baseline |
| `baseline show SUITE` | Print current baseline scores |

## Usage

### Run a suite
```bash
eval-harness run summarization
```

Override the model without editing `prompt.yaml`:
```bash
eval-harness run summarization --model openai:gpt-4o-mini
eval-harness run summarization --model groq:llama-3.1-70b-versatile
eval-harness run summarization --model together:mistralai/Mixtral-8x7B-Instruct-v0.1
```

Skip the LLM judge for a fast, cheap run:
```bash
eval-harness run summarization --no-judge
```

Check for regressions against the committed baseline:
```bash
eval-harness run summarization --check-regression
```

Export an HTML report:
```bash
eval-harness run summarization --report report.html
```

### Compare models
```bash
eval-harness compare-models summarization \
  --model together:meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo \
  --model openai:gpt-4o-mini
```

### Baselines and regression detection
```bash
# After a good run, lock it in as the baseline
eval-harness baseline set summarization
git add baselines/ && git commit -m "set eval baseline"

# Future runs will compare against it
eval-harness run summarization --check-regression
```

### CI mode
```bash
# Runs all suites, checks regression on each, exits 1 on failure/regression
eval-harness run-ci

# With HTML report
eval-harness run-ci --report report.html
```

### Add a test case
```bash
eval-harness add-case summarization
```

Interactive wizard — prompts for case ID, input variables, assertions, and rubric.

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
    ├── suite.yaml           # Optional: per-suite threshold overrides
    ├── prompt.yaml          # Prompt template ({{variable}} substitution)
    ├── prompt.v2.yaml       # Versioned variants
    └── cases/
        └── *.yaml           # One file per test case

baselines/
└── <suite-name>.json        # Committed baseline for regression detection

.eval-results/
└── <suite-name>/
    └── <run-id>.json        # Persisted run records

eval.config.yaml             # Thresholds, judge model, provider config
.github/workflows/eval.yml   # GitHub Actions — runs on every PR
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
  - type: min_length
    value: 50
  - type: contains
    value: "keyword"
  - type: not_contains
    value: "forbidden"
  - type: starts_with
    value: "The"
  - type: ends_with
    value: "."
  - type: is_json
  - type: regex
    value: "\\d{4}"
rubric: >
  Natural language description of what a good output looks like.
  Used by the LLM judge to score quality.
```

## Prompt template format

```yaml
name: my-prompt-v1
provider: together          # together | openai | groq | ollama
model: meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
system: "You are a helpful assistant."
user: |
  Summarize the following in 2-3 sentences:

  {{text}}
max_tokens: 256
temperature: 0.0
```

## Scoring

| Signal | Weight (default) |
|---|---|
| LLM-as-Judge | 70% |
| Assertion checks | 30% |

If a case has no `rubric`, the judge is skipped and assertions carry 100% of the score.

## Pass/fail thresholds

Configurable globally in `eval.config.yaml` and per-suite in `suite.yaml`:

| Condition | Default |
|---|---|
| Case passes | score ≥ 0.75 |
| Suite passes | ≥ 90% of cases pass |
| Regression | avg score drops > 0.05 vs baseline |
| Improvement | avg score rises > 0.05 vs baseline |

## Multi-provider support

Built-in providers: `together`, `openai`, `groq`, `ollama`. Add a custom one in `eval.config.yaml`:

```yaml
providers:
  my-provider:
    base_url: https://my-llm-api.internal/v1
    api_key_env: MY_PROVIDER_KEY
```

Then use it with `--model my-provider:model-name`.

## CI/CD

Add `TOGETHER_API_KEY` (or your provider's key) as a GitHub Actions secret. The workflow at `.github/workflows/eval.yml` triggers automatically on PRs that touch `suites/**`, `eval_harness/**`, or `eval.config.yaml`.

Results appear as a Markdown table in the Actions step summary. The job exits 1 if any suite fails or regresses against its baseline.
