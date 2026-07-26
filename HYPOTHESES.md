# HYPOTHESES.md — Pre-Registration Registry

**Append-only. Nothing is ever deleted or edited after its run.**
**Version:** 1.0

---

## 0. Running Counters

> Updated on every merge. These three numbers gate the validity of every claim the project
> makes.

```
Registered (registry completeness) ... 4
  ├─ Accepted ....................... 0
  ├─ Rejected ....................... 0
  ├─ Standing ....................... 1
  └─ In flight ...................... 3

N_claims (multiple-testing denom.) ... N = 2
  ├─ gates  (not counted) ........... 2   H-001, H-002
  └─ claims (counted) ............... 2   H-003, H-004

Holdout openings used ............... 0 / 3
FDR correction level ................ α = 0.05, Benjamini–Hochberg
```

In flight = status REGISTERED or RUNNING.

### Gate vs. claim

Every hypothesis is classified as exactly one of:

- **gate** — a validity or correctness condition. Asks "is the machinery sound?" A gate
  has no favourable outcome to shop for: it passes or the pipeline halts. Gates are not
  edge-seeking, cannot manufacture a false positive about profitability, and therefore do
  **not** count toward `N_claims`.
- **claim** — an edge-seeking assertion. Asks "does this work?" Every claim is a draw
  against the multiple-testing budget whether it is accepted, rejected, or abandoned.

**Only claims count toward `N_claims`.** That number, not the registered total, is the
denominator fed to the Deflated Sharpe Ratio and the Benjamini–Hochberg FDR procedure.
Counting gates would inflate the denominator with tests that cannot produce a false
positive about edge, making the correction conservative in a way that hides real failures
rather than guarding against them.

`Registered` remains the registry-completeness count and never decreases. Rejected
hypotheses count. Abandoned hypotheses count. Nothing is ever removed.

### Statuses

`REGISTERED` · `RUNNING` · `ACCEPTED` · `REJECTED` · `VOID` · `STANDING`

**`STANDING`** is for a claim enforced continuously by CI rather than answered once by a
single run. A standing hypothesis has no terminal verdict: it is asserted on every commit,
and the day it fails is the day the pipeline halts. Only gates may be `STANDING`.

---

## 1. Why This File Exists

This is **pre-registration**, borrowed from clinical trials. The problem it solves is not
dishonesty — it is the ordinary human sequence of: run experiment → see result → construct
the reason it was expected → believe the reason.

That sequence is invisible from the inside, and it is how research teams generate years of
confident, false findings. The only known defence is committing to the claim, the metric,
and the threshold **before** the data is seen.

---

## 2. Rules — Enforcement, Not Etiquette

1. **Register before running.** The hypothesis is committed to git with a timestamp
   *before* the run executes. The commit hash is the proof. A hypothesis whose registration
   commit postdates its run manifest is void.
2. **The metric and threshold are named in advance.** No metric substitution after the
   fact. Choosing the favourable metric post-hoc is `RESEARCH.md` §5.3.
3. **Rejected hypotheses stay forever.** Deleting failures recreates publication bias
   inside your own repository, and destroys the `N` that makes the successes meaningful.
4. **One hypothesis, one change.** Bundled changes produce uninterpretable results.
5. **Re-testing a rejected hypothesis requires a new ID** and increments `N` again.
6. **No exploratory result may be promoted.** If you found something while looking at data,
   register it as a *new* hypothesis and test it on data you have not seen.
7. **Holdout use is logged here**, with the reason, and decrements the budget.

---

## 3. Template

Copy this block for every new hypothesis. Fill everything above `--- RUN ---` before
committing.

```markdown
### H-000 — <short title>

- **Registered:** YYYY-MM-DD HH:MM UTC
- **Registration commit:** <hash — filled by pre-commit hook>
- **Author:** <name>
- **Status:** REGISTERED | RUNNING | ACCEPTED | REJECTED | VOID

**Claim**
> <One falsifiable sentence. "X will improve Y by ≥ Z without worsening W by > V.">

**Rationale**
> <Why this might be true. Tier 3 evidence is fine here — this is the one place it belongs.>

**Change under test**
> <Exactly one change. Files touched.>

**Primary metric & threshold**
> <e.g. Brier Skill Score improvement ≥ 0.03, bootstrap 95% CI excluding zero>

**Guardrail metrics** (must not degrade beyond stated bound)
> <e.g. Max drawdown increase ≤ 5% relative; turnover increase ≤ 20%>

**Dataset & window**
> <Explicit. Walk-forward folds, or holdout — holdout requires sign-off.>

**Sample size expected**
> <n. If < 150 decisions, K-6 applies and the run cannot conclude anything.>

**Pre-committed interpretation**
> - If PASS: <what we do>
> - If FAIL: <what we do — must be a real action, not "investigate further">
> - If AMBIGUOUS (CI straddles threshold): <default is REJECT>

--- RUN ---

- **Run manifest:** <hash>
- **Executed:** YYYY-MM-DD
- **Result:** <primary metric, value, CI, n>
- **Guardrails:** <values>
- **Baseline ladder:** <pass/fail per rung>
- **Verdict:** ACCEPTED | REJECTED
- **Notes:** <observations. Any new idea here becomes a NEW hypothesis, not an amendment.>
```

---

## 4. Seed Hypotheses

These four are registered now, before any code exists. They define the project's first
phase.

### H-001 — Pipeline integrity under shuffled labels
- **Registered:** 2026-07-26 14:32 UTC
- **Operationalisation amended:** 2026-07-26 (before any run; see §2 rule 1)
- **Class:** gate — does not count toward `N_claims`
- **Status:** REGISTERED

**Claim**
> With labels randomly permuted, the deterministic path (features → combiner) will show no
> measured edge across the 30 enumerated seeds.

**Resolution of an ambiguity in `EVALUATION.md` §5.1**

> §5.1 as originally written said the "measured edge falls **inside** the null
> distribution's 95% interval," where the null distribution is itself built from the ≥ 30
> shuffled-label seeds. That is circular: the shuffled BSS is trivially inside its own
> interval, so the condition can never fail and the gate can never fire.
>
> The reading with force, adopted here and mirrored into §5.1: **under permuted labels the
> true skill is exactly zero, so the distribution of shuffled BSS must itself be centred at
> or below zero.** Out-of-sample BSS should be slightly *negative* — a model fit on noise
> can only overfit, and overfitting costs skill. A shuffled-BSS distribution sitting
> materially above zero is the leak signature.

**Primary metric**
> Per seed `s`, `BSS_s = 1 − BS_model,s / BS_ref,s`, computed on out-of-sample predictions
> pooled across all walk-forward folds. `BS_ref,s` is the base rate (climatology) of the
> **shuffled** labels over the same pooled evaluation window, per `EVALUATION.md` §3.2.

**Pass conditions — all three must hold**

| # | Condition | Threshold |
|---|---|---|
| i | Upper bound of the 95% percentile-bootstrap CI of mean `BSS` | ≤ **0.01** |
| ii | `max_s BSS_s` | ≤ **0.05** |
| iii | median `BSS_s` | ≤ **0** |

> Bootstrap uses seed 1337 (`REPRODUCIBILITY.md` §3) with 10,000 resamples over the 30
> per-seed `BSS` values. Any failure = **K-1**.

**Registered researcher degree of freedom — ε = 0.01**

> Condition (i) is an equivalence-style bound, not a test of `E[BSS] = 0`. A strict
> one-sided test against zero is hypersensitive: with 30 seeds and low variance, a
> numerically meaningless bias of +0.0001 produces a large t-statistic and a spurious
> halt. ε = 0.01 is a materiality floor — one fifth of K-3's 0.05 skill threshold — below
> which "edge" is not a coherent claim.
>
> **ε is a judgement call.** It is recorded here, before any run, precisely so it cannot be
> chosen after seeing the numbers (`RESEARCH.md` §5.3). Changing it requires a new
> hypothesis ID.

**Seeds**
> The 30 enumerated seeds `0…29` from `REPRODUCIBILITY.md` §3 (`shuffled_labels`).
> Enumerated, not generated.

**Label**
> `direction_24`: `1` if `close[T+24] > close[T]`, else `0`. Strict inequality; ties resolve
> to `0` and the tie rate is reported. Horizon fixed at 24 bars **before** the run — trying
> h1/h4/h24 and keeping the best would be three hypotheses under `EVALUATION.md` §9 and
> metric shopping under `RESEARCH.md` §5.3.

**Fold geometry**
> Expanding-window walk-forward, 5 folds. Purge and embargo per `EVALUATION.md` §5.2 with
> `H = 24`: training samples whose label window `[T, T+24]` reaches the test window are
> dropped (purge); a 24-bar buffer following each test window is excluded from later
> training (embargo). Evaluation decisions are spaced 24 bars apart (non-overlapping)
> within each test fold, so the reported `n` counts effectively independent decisions
> rather than 24× overlapping restatements of the same bet.

**Estimator**
> Hand-rolled logistic regression, fixed iteration count, no `scikit-learn`. Ships with a
> capability test: given the label itself as a feature it must reach near-perfect BSS. A
> combiner that cannot detect a planted leak cannot be trusted to report its absence.

**Scope of the deterministic path**
> Features → combiner, per the `REPRODUCIBILITY.md` §6 practical note ("run the
> shuffled-labels gate on the deterministic path (features → stacker), not the full LLM
> path"). No agents, no LLM. An LLM in the shuffling loop would add non-determinism to the
> exact test that measures noise.

**Pre-committed interpretation**
> - PASS: proceed to H-002.
> - FAIL: **K-1 halt.** Full leakage audit. No other work proceeds.

**Data requirement**
> A verdict on H-001 requires real market data. Runs against `src/data/synthetic.py` are
> `run_type: harness_validation`, carry `hypothesis_id: null`, and **may never be cited as
> evidence for H-001**. Synthetic bars have no vintages, no revisions, no session
> boundaries, no DST, no gaps and no missing bars, so they cannot exercise the
> `DATA_CONTRACT.md` §3/§4/§6 hazards that a real ingestion layer introduces.

---

### H-002 — Temporal causality of all features

- **Registered:** 2026-07-26 14:32 UTC
- **Class:** gate — does not count toward `N_claims`
- **Status:** STANDING

**Claim**
> Every feature recomputed on data truncated at bar `T` will be bit-identical to its value
> in the full-history computation at bar `T`.

**Primary metric & threshold**
> 100% of features pass. Any failure = FAIL.

**Pre-committed interpretation**
> - FAIL: **K-2 halt.** The failing feature is disabled until fixed.

--- STANDING ---

- **Enforced by:** `tests/test_causality.py` (registry-wide sweep) and
  `tests/features/test_<name>.py` (per feature, `CLAUDE.md` Hard Rule 1).
- **Gate:** `.github/workflows/ci.yml`, step "Causal feature test (K-2)" — runs on every
  push and pull request. Also enforced locally by `hooks/pre-push`.
- **Why STANDING and not ACCEPTED:** this claim is not answered once. It is asserted on
  every commit against whatever the feature registry contains at that commit, and it must
  be re-asserted every time a feature is added. `tests/test_causality.py` fails the build
  if a module under `src/features/` is absent from `FEATURE_REGISTRY`, so the sweep cannot
  silently narrow. An `ACCEPTED` verdict would freeze a result that is only true of the
  feature set at the moment it was recorded.
- **Current scope:** every module in `src/features/`. The day this fails is the day the
  pipeline halts under K-2.

---

### H-003 — Signal beats random entry

- **Registered:** 2026-07-26 14:32 UTC
- **Class:** claim — counts toward `N_claims`
- **Status:** REGISTERED

**Claim**
> A single-agent deterministic baseline will beat random entry with identical risk
> management at p < 0.05 over ≥ 150 decisions.

**Primary metric & threshold**
> Difference in expectancy per trade, bootstrap p < 0.05.

**Pre-committed interpretation**
> - PASS: the signal contains information. Proceed to build the agent panel.
> - FAIL: **K-4.** The architecture is not the problem — the signal is. Do not add agents;
>   adding agents to a signal with no information produces a more expensive way to be
>   wrong. Return to feature research.

---

### H-004 — LLM synthesis vs. deterministic combination (SC-1)

- **Registered:** 2026-07-26 14:32 UTC
- **Class:** claim — counts toward `N_claims`
- **Status:** REGISTERED

**Claim**
> LLM synthesis over agent outputs will achieve a BSS at least 0.03 higher than a logistic
> regression stacker trained on the same agent outputs.

**Guardrails**
> Cost per decision, and run-to-run variance at temperature 0.

**Pre-committed interpretation**
> - PASS: LLM stays in the decision path.
> - FAIL: **LLM is removed from the decision path** and retained only for narrative
>   generation and journalling. This is not a downgrade — it buys full reproducibility.
> - AMBIGUOUS: REJECT. Tie goes to the cheaper, deterministic, interpretable method.

---

## 5. Registry

> New entries appended below. Never reordered. Never removed.

<!-- H-005 onward -->
