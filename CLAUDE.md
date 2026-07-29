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
| 4 | **Kill criteria are immutable.** `EVALUATION.md` §1 is never edited, relaxed, or reinterpreted. If a criterion trips, the correct action is to stop, not to adjust the criterion. A kill criterion is a research-validity condition. Tripping one means a result is invalid and work halts. Engineering-hygiene gates — lint, format, type check — are not kill criteria and must never be assigned a K-code; they cite this file's Style section. Failing them means fix and re-push, not halt. Do not extend the §1 table to cover code quality. |
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

## `src/risk` — the risk and cost layer, and why it is outside all of the above

**Settled. Do not re-litigate.** This section exists so that the next person reading `src/risk` does not have to work out from first principles whether it belongs to the research programme. It does not.

### What it is

Deterministic accounting on live MT5 account state, addressing the two mechanisms that actually emptied the account this project has a user for: an unbounded drawdown, and a two-month hold whose financing cost consumed what the drawdown left. Per-position carry, cumulative cost since entry, time in trade, projected days to the broker's stop-out, position sizing from a risk percentage and ATR, a daily loss limit and a cap on concurrent positions.

Neither mechanism is a prediction problem, and neither is addressed by having a signal.

### The reading

| | |
| :---- | :---- |
| **Joins no pipeline** | Nothing under `src/backtest`, `src/data`, `src/evaluation`, `src/features`, `src/labels`, `src/metrics` or `src/models` imports it. The dependency runs one way: `risk` imports the two registered swap constants from `backtest.costs` **in order to compare against them**, and nothing else. |
| **Makes no market claim** | No `hypothesis_id`, no registration, **no `N_claims` draw**. `N_claims` stays at 6. Nothing this layer produces may be cited for or against anything in `HYPOTHESES.md`. |
| **Predicts nothing** | No direction, no probability, no signal, no edge, and no view on whether a trade is a good idea. Days-to-stop-out is arithmetic under a stated constant-price assumption — a bound, not a forecast. |
| **Never trades** | `order_send` appears nowhere in this repository, per `RESEARCH.md` §2. Every MT5 call is a read or a pure calculation. |
| **Needs no backtest** | It is arithmetic on published account state. It needs tests, and has them. A backtest of it would be a backtest of addition. |

### What that changes about the rules

Hard Rule 1 (causal tests) governs **features**. There are none here. Hard Rules 3, 4, 7, 8 and 9 govern **registered evaluation runs**. This layer produces none.

The constants in `src/risk/config.py` — 1% per trade, 3% a day, 2 positions, a 48-hour alert — are **operating limits on a live account, not parameters of a claim.** Changing one requires no procedure beyond deciding to, and `RESEARCH.md` §5.2 on post-hoc constant changes does not apply to them. They are provisional pending the probe. This is the opposite of `EVALUATION.md` §1 and of H-008's fixed sweep, and the difference is the point.

Hard Rules 2, 6 and 10, and everything in Style, apply here exactly as everywhere else.

### The one thing this layer says *about* the registry

`backtest.costs` charges 20 points long and 8 short. Those are H-005's **pessimistic substitute**, chosen when the feed could not be calibrated — never this broker's rate.

**It has now been read. `HYPOTHESES.md` H-005, 2026-07-29, is the record; this is the summary.** FxPro `GOLD` reports `swap_mode = 2` (`CURRENCY_SYMBOL`), `swap_long = -67.9`, `swap_short = +27.0`. Three findings, different in kind:

1. **The structure is wrong.** A base-currency rate makes the account-currency charge proportional to the gold price. The registered model has no term that varies with price, so **no value of the constant would have been right.** The layer's *refusal* to convert is what surfaced this — a default would have buried it inside a plausible number.
2. **The sign is asymmetric.** Long pays, short is credited. `swap_points` charges both directions on the stated ground that a credit is an optimistic assumption about an unobserved rate. It is now observed.
3. **The magnitude is roughly 3.4x long**, under a reading the field alone cannot confirm. A week of a real position settles it.

`SwapDivergence` is a **first-class field of the risk report** rather than a diagnostic, and it is reported on three bases. The one to trust for a price-dependent mode is **annualised percent of notional**, because it is the only basis invariant to the price.

`bears_on_the_registry` is true whenever the mode is price-dependent, **whether or not the magnitude comes out high** — a substitute that is wrong in structure bears on the registry regardless.

### A correction, kept because the pattern is the point

An earlier version of this section claimed `rollovers_crossed` "counts five rollovers a week and has no triple-swap concept", so the registered model understated a week's carry by two sevenths. **That was wrong.** It was asserted from the function's name without reading its body.

`[MEASURED]` `rollovers_crossed` counts **every** calendar day's boundary, weekends included — 7 per week, 14 per fortnight. The registered night **count** is right; only the *timing* differs, and it cancels over whole weeks. `tests/risk/test_clock.py` now measures the count against the real function, so the layer's comparison basis is pinned rather than believed.

The lesson is the same one §8 taught: **an assertion about someone else's code that is not a test is an assertion you are relying on luck for.** The magnitude and sign findings above survive this correction untouched.

### Enforcement

`RETROSPECTIVE-2.md` §1.2: **a rule that is not a test is a rule you are relying on luck to follow.** Every statement above is asserted in `tests/risk/test_scope.py` and fails the build rather than decaying into prose.

### Acceptance

`scripts/risk_monitor.py --probe` on a **demo** account, on Windows. Until the adapter has been read against a live terminal once it is unverified, and nothing that depends on it should be trusted. The probe prints every field read, the provenance of every derived number, and every refusal.

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
