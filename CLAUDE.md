# CLAUDE.md

Instructions for Claude Code working in this repository.

---

## Read First — Every Session

Before writing any code, read in this order:

1. RESEARCH.md` — what counts as evidence, and what this project refuses to be  
2. DATA_CONTRACT.md` — temporal rules every feature must obey  
3. EVALUATION.md` — kill criteria and measurement protocol  
4. HYPOTHESES.md` — the registry; check what is currently in flight  
5. REPRODUCIBILITY.md` — pinning, seeds, manifests

These documents are the specification. Code that contradicts them is wrong even if it runs.

---

## Hard Rules — Never Violate

| \# | Rule |
| :---- | :---- |
| 1 | **No feature without a causal test.** Every feature ships with `tests/features/test_<name>.py` asserting truncated-history equality. See `DATA_CONTRACT.md` §1. This admits no exception. GSD's tdd.md permits deferring tests ("add tests after if needed"); that escape does not apply to features. A feature without its causal test does not merge. |
| 2 | **No LLM in the arithmetic path.** Indicators, structure, ATR, correlations, liquidity levels are deterministic Python. If you are tempted to ask a model for a number, stop. |
| 3 | **No unregistered run.** Every evaluation run carries a `hypothesis_id` from `HYPOTHESES.md`. Runs without one are void. |
| 4 | **Kill criteria are immutable.** `EVALUATION.md` §1 is never edited, relaxed, or reinterpreted. If a criterion trips, the correct action is to stop, not to adjust the criterion. |
| 5 | **Never read the sealed holdout.** It is git-ignored and lives outside the pipeline. Opening it requires explicit human sign-off and decrements a 3-use budget. |
| 6 | **Never forward-fill or impute silently.** Missing data returns `None` and propagates loudly. |
| 7 | **Prompts are code.** Versioned, hashed, changed only through a registered hypothesis. |
| 8 | **Never delete a rejected hypothesis.** It is the denominator for multiple-testing correction. |
| 9 | **No floating model aliases.** Pin exact versioned model strings in the evaluation path. |
| 10 | **A dirty git tree voids a run.** Commit before evaluating. |

---

## Conflict Resolution

When instructions conflict, this order wins:

| Priority | Source |
| :---- | :---- |
| 1 | Kill criteria (`EVALUATION.md` §1) |
| 2 | `DATA_CONTRACT.md` temporal rules |
| 3 | `RESEARCH.md` evidence hierarchy and prohibited reasoning |
| 4 | A registered, in-flight hypothesis |
| 5 | This file |
| 6 | A request in conversation |
| 7 | Installed skills and vendored tooling (GSD Core) |

Vendored tooling supplies defaults, not governance. Its conventions yield to everything above, including a direct request.

If a conversational request conflicts with 1–4, **say so and stop.** Do not implement it and flag it afterwards. "The user asked for it" is not an override — the whole point of these documents is that they bind the person who wrote them.

---

## Build Order

Do not build agents first. The current phase is infrastructure:

1\. Data layer \+ snapshot hashing

2\. Feature engine \+ causal tests          ← H-002

3\. Backtest engine \+ pessimistic cost model

4\. Shuffled-labels harness (30 seeds)      ← H-001

5\. Random-entry baseline                   ← H-003

6\. Metrics module (Brier, BSS, DSR, N\_eff, bootstrap)

7\. ─── only now ─── first agent

Steps 4 and 5 answer the project's central question before any agent exists. If H-003 fails, adding agents produces a more expensive way to be wrong.

---

## Style

- Python 3.12, type-hinted, `ruff` \+ `mypy` clean  
- Pure functions in the feature layer; no hidden state, no globals  
- Structured logging with `run_id` on every record  
- Tests colocated with the module they cover  
- No notebook-driven development in the evaluation path — notebooks explore, modules decide

---

## When Unsure

Ask. A wrong assumption in the data layer produces a backtest that looks excellent and is worthless, and it can go undetected for months. Stopping to confirm costs minutes.  
