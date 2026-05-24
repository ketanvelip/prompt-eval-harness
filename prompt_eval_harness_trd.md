# Prompt Eval Harness — Technical Requirements Document

**Version:** 1.0.0  
**Status:** Draft  
**Date:** May 24, 2026  

---

## 1. Overview

### Problem

Prompt iteration today is manual and unreliable. Engineers change a prompt, test a few examples by hand, decide it "feels better," and ship — with no record of what was tested and no way to know if something else broke.

This leads to silent regressions, no shared baseline, and a growing fear of touching prompts that are working well enough.

### Goal

A CLI tool that automatically runs a prompt against a defined set of test cases, scores the outputs, and tells the engineer clearly whether the change was an improvement, a regression, or neutral — in under 60 seconds.

### Non-Goals

- No web UI in v1
- Does not deploy prompts to production
- Does not fine-tune models
- Single model provider to start (Anthropic Claude)

---

## 2. Functional Requirements

### 2.1 Test Cases

- Engineers define test cases as structured files (input + expected qualities)
- Each case specifies what a good output looks like, not an exact expected string
- Cases are versioned alongside the prompts they test
- Suites group related cases (e.g. all summarization cases together)

### 2.2 Running Evals

- Run a suite against any prompt version from the command line
- Support prompt templates with variable substitution
- Record every output, score, and latency for each run
- Compare any two runs to show score delta

### 2.3 Scoring

Each output is scored using two methods:

**LLM-as-Judge** — a separate model call rates the output against the case rubric on a 0–1 scale and returns a brief reason. This is the primary signal.

**Assertion Checks** — programmatic pass/fail rules (e.g. max length, must contain a phrase, must be valid JSON). These catch hard failures the judge might miss.

The final score is a weighted combination of both.

### 2.4 Results

- Results are stored locally after every run
- History view shows score trend over time for a suite
- Compare view diffs two specific runs side by side
- Terminal report shows per-case pass/fail with scores and reasons

### 2.5 Pass/Fail Thresholds

| Condition | Threshold |
|---|---|
| Case passes | Score ≥ 0.75 |
| Suite passes | ≥ 90% of cases pass |
| Regression | Avg score drops > 0.05 vs baseline |
| Improvement | Avg score rises > 0.05 vs baseline |

Thresholds are configurable per project.

---

## 3. CLI Interface

```
run      Run a suite against a prompt version
compare  Diff two result files
history  Show score trend for a suite over time
add-case Add a new test case to a suite interactively
```

---

## 4. Constraints

- Must work fully offline except for API calls
- API key configured via environment variable, never hardcoded
- Results stored locally — no external database
- Judge model should be cost-efficient (small/fast model)
- All test cases and prompts must be human-readable and git-friendly

---

## 5. Build Phases

### Phase 1 — Core Pipeline
Runner + assertion scoring + result storage + basic CLI. End-to-end with a single test case.

### Phase 2 — LLM Judge + Compare
Add judge scoring, weighted final score, compare command, formatted terminal output.

### Phase 3 — Suites + History
Built-in starter suites, add-case command, history view, configurable thresholds.

### Stretch
- CI/CD integration (run evals on every PR)
- Multi-model support
- HTML report export

---

## 6. Open Questions

| Question | Notes |
|---|---|
| Judge model quality vs cost | A cheap model may miss subtle regressions. Should engineers be able to opt into a more capable judge for high-stakes evals? |
| Parallel execution | Running cases in parallel speeds things up but complicates rate limiting. Worth it? |
| Test case ownership | Cases should live in the same repo as the prompts. Who is responsible for keeping them current? |
| Result storage | JSON files are simple but hard to query at scale. When does it make sense to move to SQLite? |

---

## 7. Success Metrics

- A 50-case suite completes in under 60 seconds
- At least one regression is caught that would otherwise have shipped
- The team uses it for the majority of prompt changes within 4 weeks
- Score trends show measurable improvement over 30 days of use
