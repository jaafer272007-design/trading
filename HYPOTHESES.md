# HYPOTHESES.md — Pre-Registration Registry

**Append-only. Nothing is ever deleted or edited after its run.**
**Version:** 1.0

---

## 0. Running Counters

> Updated on every merge. These three numbers gate the validity of every claim the project
> makes.

```
Registered (registry completeness) ... 8
  ├─ Accepted ....................... 2   H-001 (K-1, 2026-07-27)
  │                                       H-003 (K-4, 2026-07-28) — see note
  ├─ Rejected ....................... 1   H-007 (rung 2, 2026-07-28)
  ├─ Standing ....................... 1
  └─ In flight ...................... 4

N_claims (multiple-testing denom.) ... N = 3
  ├─ gates  (not counted) ........... 5   H-001, H-002, H-005, H-006, H-008
  └─ claims (counted) ............... 3   H-003, H-004, H-007

Holdout openings used ............... 0 / 3
FDR correction level ................ α = 0.05, Benjamini–Hochberg
```

> **Note on H-003, 2026-07-28 — why it is marked "see note".** Registering H-007 moved
> `N_claims` from 2 to 3, which under `EVALUATION.md` §9 moved the Benjamini–Hochberg
> rank-1 critical value from 0.025 to 0.0167. H-003's `p = 0.0204` stopped clearing on its
> own, and BH being step-up, its survival became contingent on H-007 returning
> `p ≤ 0.0333`. That was registered before H-007 ran.
>
> **H-007 returned `p = 0.5041`.** BH rejects nothing in the family: H-003 does not clear
> §9. Separately and more importantly, H-007 measured always-long matching the signal, so
> **H-003's directional reading is withdrawn** — see the appended block at the end of its
> entry.
>
> `Status: ACCEPTED` is left in place on purpose. The run happened and its arithmetic
> holds; what failed is the inference drawn from it, and the registry records what was
> done rather than what is currently believed.

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
- **Fold geometry amended:** 2026-07-27 (before any run — `FIRST_TEST_FRACTION = 0.50`)
- **Executed:** 2026-07-27 on real market data
- **Class:** gate — does not count toward `N_claims`
- **Status:** ACCEPTED — K-1 does not trip

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

**Amended 2026-07-27, before any run: the split point, registered**

> The clauses above fix the fold *count*, the purge and embargo rule, and the decision
> spacing. They do not fix **where the first test window opens**, and the first real-data
> setup silently chose half the series. That is a researcher degree of freedom and it is
> registered here rather than left in a constant, on the same footing as ε = 0.01: a
> geometry decided after a run is geometry chosen to suit a result.
>
> **`FIRST_TEST_FRACTION = 0.50`.** The first test window opens at the midpoint of the
> in-window series; the remainder is divided into 5 equal test windows.
>
> ---
>
> **What could have selected it, and what actually does**
>
> `[MEASURED]` `scripts/report_fold_geometry.py` over the H-001 snapshot, 65,395
> in-window bars, 64,886 eligible. Nothing below involves labels or skill — every figure
> is a property of the calendar and the eligibility mask, identical under any labels at
> all.
>
> | split | pooled decisions | per fold | × K-6 | train fold 0 | rows/param | eras in test |
> |---|---|---|---|---|---|---|
> | 0.30 | 1,894 | 370–382 | 12.6 | 19,474 | 4,868:1 | 2 |
> | 0.40 | 1,632 | 324–327 | 10.9 | 25,722 | 6,430:1 | 2 |
> | **0.50** | **1,364** | **272–273** | **9.1** | **32,188** | **8,047:1** | **2** |
> | 0.60 | 1,090 | 218 | 7.3 | 38,728 | 9,682:1 | 2 |
> | 0.70 | 819 | 163–164 | 5.5 | 45,267 | 11,316:1 | **1** |
>
> Two of the three plausible criteria turn out not to bind, and saying so is more useful
> than picking the number each happens to favour:
>
> - **K-6 headroom** (`EVALUATION.md` §1: fewer than 150 closed decisions is *no result*).
>   Every candidate clears it by 5.5× or more pooled, and by 1.1–2.5× per fold. It does
>   not discriminate.
> - **Training-window adequacy.** The combiner is three features plus an intercept. Even
>   the smallest pool is 4,868 rows per parameter — three orders of magnitude of slack.
>   It does not discriminate either. Anyone reaching for "more training data" as the
>   reason for a later split is reaching for a constraint that is not active.
> - **Era composition** *does* discriminate, at one end. A split at or past **0.661** —
>   where the 2022-10-21 era begins — confines the entire test set to a single era and
>   makes H-006's era term unmeasurable out-of-sample. That rules out 0.70 and everything
>   after it. It does not distinguish 0.30 from 0.60.
>
> **So the criteria bracket the choice to 0.30–0.60 and do not select inside it.** 0.50 is
> registered on two grounds, both of which are weaker than a measurement and are stated as
> such:
>
> 1. It is the maximin split — it maximises the smaller of the training and testing halves,
>    which is the assumption-free choice when nothing else discriminates.
> 2. **It is the value the dry run already published.** Moving to 0.30 now, having seen
>    that it yields 1,894 decisions instead of 1,364, would be selecting geometry on a
>    number produced after the setup was fixed. `n` is not binding, so there is nothing to
>    buy — and buying it anyway is `RESEARCH.md` §5.3 in miniature.
>
> ---
>
> **Where the split lands, and which folds cross an era boundary**
>
> `[MEASURED]`, same run. The split falls at position **32,697 = 2021-02-08 20:00 UTC**,
> which is **inside** the 2017-10-07 era, not on a boundary.
>
> | fold | test window (UTC) | n | train | test era composition |
> |---|---|---|---|---|
> | 0 | 2021-02-08 → 2022-03-02 | 273 | 32,188 | 2017-10-07 100% |
> | 1 | 2022-03-02 → 2023-03-30 | 273 | 38,727 | **2017-10-07 60.4% / 2022-10-21 39.6%** |
> | 2 | 2023-03-30 → 2024-05-08 | 273 | 45,266 | 2022-10-21 100% |
> | 3 | 2024-05-08 → 2025-06-17 | 273 | 51,805 | 2022-10-21 100% |
> | 4 | 2025-06-17 → 2026-07-27 | 272 | 58,344 | 2022-10-21 100% |
>
> **Fold 1 straddles 2022-10-21.** Its test window contains the return of the daily break,
> so a single fold is scored across two session structures.
>
> **Three folds are worse than that, and it is not the straddle.** Folds 2, 3 and 4 train
> on a pool that is 67%, 59% and 52% pre-2022 respectively, and test **entirely** in the
> 2022-10-21 era. Their training and test halves sit in different session regimes. That is
> exactly the condition H-006's era term was added to make visible, and it is now visible
> in the geometry rather than only in the data.
>
> This is recorded, not avoided. Avoiding it requires either moving the split past 0.661 —
> which confines the whole test set to one era, a strictly larger distortion — or aligning
> fold edges to era boundaries, which would make fold sizes a function of the calendar and
> couple the evaluation geometry to a declaration that `REVIEW_ITEMS.md` **R-001** says is
> not yet externally confirmed.
>
> **The 2015-09-11 era never appears in a test window** under any split at or above 0.187.
> It is training data in every fold. The era term is therefore not estimable out-of-sample
> on that era under this geometry — a limitation of the geometry, not of the term, and one
> that matters for a skill claim rather than for this gate.
>
> ---
>
> **What this does and does not affect for H-001 specifically**
>
> Under permuted labels there is no signal, so era composition cannot change what H-001
> measures: every era is noise once the labels are shuffled, and all three features are
> session-invariant (measured — `tests/test_causality.py` recomputes each on a scrambled
> index and requires bit-identical output). The geometry matters here because **H-001
> certifies the geometry it runs under.** A later evaluation using a different split does
> not inherit this gate's result, which is the reason to register the number now rather
> than to treat it as an implementation detail.
>
> **Guardrail.** `FIRST_TEST_FRACTION` may not be changed after a run without a new
> hypothesis ID. Re-running H-001 at a different split and reporting whichever passes is
> `EVALUATION.md` §9 — as many hypotheses as splits tried — and `RESEARCH.md` §5.3.

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

--- RUN ---

- **Run manifest:** `runs/8838059a-56eb-43dd-b643-e4ccfc0f79b3.json`
  sha256 `b6daca9ac1eb977fa8300f2ef78c742fa4be1d5c8e8aa274ecd6ce7586534c48`
- **run_id:** `8838059a-56eb-43dd-b643-e4ccfc0f79b3`
- **Executed:** 2026-07-27, commit `ae33621`, `git_dirty: false`
- **Registration precedes the run:** geometry amendment committed `43dafa2` at
  2026-07-27T22:11:44Z, merged to main as `a0dda23`. §2 rule 1 satisfied.
- **Data:** `GOLD-H1-20080311-20260727.csv`, derived snapshot
  `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6`.
  65,395 in-window bars, 64,886 eligible, 1,364 pooled decisions.
- **Verdict:** **ACCEPTED — K-1 does not trip.**

**Result — the null distribution, 30 seeds, 1,364 decisions each**

> ```
> s2  -0.002799  s25 -0.002566  s19 -0.002184  s13 -0.002170  s22 -0.001826  s5  -0.001379
> s29 -0.001318  s11 -0.001262  s21 -0.001203  s12 -0.001031  s28 -0.000844  s7  -0.000822
> s8  -0.000782  s15 -0.000762  s10 -0.000744  s20 -0.000724  s6  -0.000631  s3  -0.000609
> s17 -0.000507  s0  -0.000504  s23 -0.000443  s14 -0.000429  s26 -0.000315  s18 -0.000291
> s9  -0.000229  s24 -0.000140  s16 -0.000121  s1  +0.000033  s27 +0.000202  s4  +0.000757
> ```
>
> min −0.002799 · max +0.000757 · sd 0.000815 · 3 of 30 seeds above zero
>
> The distribution sits where §5.1 says it must under permuted labels: centred
> slightly below zero, because a model fit on noise can only overfit and
> overfitting costs skill. The three positive seeds are two and three orders of
> magnitude below ε.

**Pass conditions — measured**

> | # | Condition | Threshold | Measured | |
> |---|---|---|---|---|
> | i | 95% bootstrap CI upper bound of mean BSS | ≤ 0.01 | **−0.000577** | pass |
> | ii | `max_s BSS_s` | ≤ 0.05 | **+0.000757** | pass |
> | iii | median `BSS_s` | ≤ 0 | **−0.000734** | pass |
>
> mean BSS −0.000855, 95% CI [−0.001156, −0.000577], bootstrap seed 1337,
> 10,000 resamples. All three hold. **K-1 does not trip.**

**Unshuffled control — reported alongside, not part of the verdict**

> Same pipeline, same folds, true labels: **BSS = −0.006766** on n = 1,364.
>
> **It is worse than the shuffled null**, by roughly 8× the null's mean. That is
> stated because it is what happened, not explained away: this three-feature
> combiner extracts nothing directional at H = 24 on this data, and fitting real
> labels costs more out-of-sample than fitting noise does — a spurious in-sample
> relationship that does not survive the fold boundary.
>
> This is **not** a K-3 result. K-3 lives on the sealed holdout, which has not
> been opened, and no cost model, baseline ladder, or random-entry comparison
> (H-003) has run. It is not evidence for or against any edge claim and must not
> be cited as one. It is recorded here because a shuffled-label null is
> uninterpretable without knowing what the same machinery does on real labels.

**Leak fixtures — both trip, as required**

> | fixture | mean BSS | max | outcome |
> |---|---|---|---|
> | `label_in_features` | +0.999984 | +0.999984 | **TRIPPED** |
> | `target_encoding_on_all` | +0.247319 | +0.277759 | **TRIPPED** |
>
> The gate is demonstrably capable of firing on this data, this geometry, and
> this combiner. Without these the verdict above would be a statement about the
> estimator's weakness rather than the pipeline's integrity.

**K-1 sensitivity at this capacity**

> Combiner fingerprint `9b09e2482278a57a…`, 4 parameters (3 features +
> intercept). Baseline run `5c6c585b-7531-48bd-945c-8c077b759a05` at commit
> `7d6ed38b` — synthetic, `harness_validation`, never evidence for H-001.
>
> | mode | recorded mean BSS | trips at 4 params |
> |---|---|---|
> | `label_in_features` | +0.999984 | yes |
> | `target_encoding_on_all` | +0.239781 | yes |
> | `train_test_overlap` | −0.000901 | **no** |
> | `scaler_fit_on_all` | −0.001390 | **no** |
>
> `train_test_overlap` is a genuine leak that a four-parameter linear combiner
> lacks the capacity to exploit. **This pass therefore certifies that no label
> reaches the model. It does not certify the absence of all leakage**, and the
> standing-limitation clause below enumerates what it misses.

**Notes**

> Fold 1's test window straddles the 2022-10-21 session-era boundary, and folds
> 2–4 train on predominantly pre-2022 pools while testing entirely after it.
> Under permuted labels that cannot affect the measurement — there is no signal
> to be regime-dependent about — but it is the geometry a later skill claim
> would inherit, and it is recorded in the amendment above rather than left to
> be rediscovered.
>
> Embargo removed 0 training bars beyond purge. Expected under forward-only
> tiling and reported rather than listed as an applied control.

**Data requirement**
> A verdict on H-001 requires real market data. Runs against `src/data/synthetic.py` are
> `run_type: harness_validation`, carry `hypothesis_id: null`, and **may never be cited as
> evidence for H-001**. Synthetic bars have no vintages, no revisions, no session
> boundaries, no DST, no gaps and no missing bars, so they cannot exercise the
> `DATA_CONTRACT.md` §3/§4/§6 hazards that a real ingestion layer introduces.

**Standing limitation — what a K-1 pass does and does not certify**

> `train_test_overlap` does not trip at the current combiner capacity. Measured over 30
> seeds and 834 pooled decisions: mean BSS −0.000901, gate silent. It is a genuine and
> serious leak; the combiner simply has four parameters (three features plus an
> intercept) and cannot memorise the 167 overlapped rows needed to exploit it.
>
> **A K-1 pass therefore certifies that no label reaches the model. It does not certify
> the absence of all leakage.** Specifically, it does not cover:
>
> - **train/test overlap** — below capacity here; a higher-capacity stacker would trip on
>   it (`REPRODUCIBILITY.md` §6).
> - **purge or embargo defects** — global permutation destroys the autocorrelation those
>   controls exist for, so the gate is structurally blind to them regardless of capacity.
>   Needs the separate integrity check at `REPRODUCIBILITY.md` §6 Tier 1 step 4.
> - **features that peek at future prices** — shuffling labels leaves features untouched.
>   That is §5.3 / K-2's job.
>
> Sensitivity is a property of the combiner, not of the gate, and is re-measured and
> enforced on every combiner change — see `REPRODUCIBILITY.md` §6 and
> `src/evaluation/sensitivity.py`.

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
- **Operationalisation amended:** 2026-07-28 — before any run, and before the backtest
  engine exists (see §2 rule 1)
- **Cost constants amended:** 2026-07-28 — still before any run, after the engine was
  built to §I and introduced constants the specification could not have named (§J–§N)
- **Executed:** 2026-07-28 on real market data
- **Class:** claim — counts toward `N_claims`
- **Status:** ACCEPTED — K-4 does not trip

**Claim**
> A single-agent deterministic baseline will beat random entry with identical risk
> management at p < 0.05 over ≥ 150 decisions.

**Primary metric & threshold**
> Difference in expectancy per trade, bootstrap p < 0.05.

---

**Amended 2026-07-28, before any run: what "the signal", "random entry" and "identical
risk management" actually are**

> The claim names three objects and defines none of them. `CLAUDE.md` Build Order step 3
> is the backtest engine, and an engine written before this specification would fix all
> three by implementation — after which registering them is transcription, not
> pre-commitment. H-001's split point was the same failure caught one step later. This is
> the same discipline applied one step earlier: **the engine is written to this entry, not
> this entry to the engine.**
>
> Every geometry figure below is a property of the calendar and the eligibility mask,
> identical under any labels at all. That is why it can be stated in advance without
> peeking at anything.

**A — The signal under test**

> | element | value |
> |---|---|
> | features | `log_return_24`, `realized_vol_24`, `range_position_48` |
> | combiner | hand-rolled logistic regression, fixed iteration count, fit per fold on training rows only |
> | direction | long if `p > 0.5`, short if `p < 0.5` |
> | `p == 0.5` exactly | **no trade.** Counted and reported separately |
>
> Identical to the deterministic path K-1 cleared, and identical for a reason: **K-1 does
> not certify "the pipeline", it certifies a path** — those three features, that combiner,
> that fold geometry. A different feature set here would be an object no gate has cleared,
> and the K-1 result could not be cited for it.
>
> **`atr_14` is deliberately excluded from the signal** although it is registered and
> passes H-002 on every commit. It sets the stop distance under §D. A feature that both
> sizes the risk and votes on the direction couples the two things rung 1 exists to
> separate.

**B — Decision times: already fixed, label-free, and sufficient for K-6**

> Not a new choice. `evaluation/splits.py` already spaces test decisions `horizon` bars
> apart — `all_idx[test_start:test_end:24]`, filtered by the eligibility mask. It is the
> grid H-001 ran on, unchanged.
>
> `[MEASURED]` `scripts/report_fold_geometry.py`, snapshot `71f9fcf1…`, at the registered
> `FIRST_TEST_FRACTION = 0.50`:
>
> | | pooled | per fold |
> |---|---|---|
> | decisions | **1,364** | 272–273 |
> | × K-6 floor (150) | 9.1 | 1.8 |
>
> **K-6 is answered before the run rather than discovered after it.** Eligibility is
> `label_validity & feature_validity & isfinite`, and none of those reads a label *value*,
> so the count is invariant under any permutation of the labels. Stating it in advance is
> not a peek — it is the same argument that licensed the fold-geometry sweep.
>
> Both arms trade at exactly these 1,364 timestamps. **The comparison is paired.**
>
> **No entry filter and no confidence threshold: τ = 0, registered.** Every grid point
> produces a trade. This is the minimum-degrees-of-freedom choice — a threshold
> `|p − 0.5| ≥ τ` is a constant somebody picks, and picking it after seeing decision
> counts or returns is `RESEARCH.md` §5.3 with extra steps.
>
> **What τ = 0 costs, stated because it is a real limitation and not a footnote.** H-003
> cannot detect a signal whose value lies in *when* to trade rather than *which way*. If
> the combiner's information is concentrated in its confident calls, trading all 1,364
> dilutes it, and H-003 is then a conservative test that can fail on a signal a threshold
> would have found. Thresholding is a separate hypothesis and needs a separate ID.

**C — The control: what "random entry" means here**

> Same 1,364 timestamps, same risk management, direction drawn uniform over
> `{long, short}` from seed stream `random_entry: [0..29]` (`REPRODUCIBILITY.md` §3, added
> by this amendment). Thirty arms, matching H-001's sweep, reported as a distribution and
> never as a single seed.
>
> **Rejected alternative, recorded: randomising the entry *times* as well.** §2 rung 1
> isolates exactly one question — is the edge in the signal or in the stop/target geometry?
> Randomising times changes two things at once and the difference stops attributing to
> either. Holding times fixed also removes calendar luck from the comparison outright
> rather than averaging it away across seeds.

**D — "Identical risk management", specified**

> | element | value | why this and not something else |
> |---|---|---|
> | stop | `1.5 × ATR(14)` at entry | wide enough that ordinary H1 noise does not dominate the exit |
> | target | `1.5 × ATR(14)` | **symmetric.** An asymmetric target embeds a payoff-shape bet in the geometry — the thing rung 1 holds constant — and hands the random arm a non-zero gross expectancy, which would make the control itself a strategy |
> | time exit | 24 bars | the label horizon: a decision closes where the thing it predicted resolves |
> | entry fill | **open of bar `T+1`** | the signal is computed on bar `T`'s close. Filling at that close is a zero-latency assumption and §10 forbids it |
> | exit fill | worse of the level and the next bar's open | §10 gap-through: stops do not fill at the stop price |
> | intrabar ambiguity | if one bar's range contains **both** stop and target, the **stop** is taken | H1 bars carry no intrabar path. The pessimistic resolution is the only one §10 permits |
> | sizing | risk-normalised, `size = R / (1.5 × ATR)`, `R` constant | expectancy per trade is the metric; unnormalised size makes it a function of the ATR regime rather than of the signal |
>
> "Identical" is enforced structurally rather than by inspection: both arms call one
> position-lifecycle function and differ only in the direction argument. A test asserts
> that swapping the direction source leaves every other field of the decision record
> unchanged.

**E — Costs, and a partial invariance that must be measured rather than assumed**

> `EVALUATION.md` §10 under H-005's registered substitute: 75-point spread floor, §10's
> session and event multipliers on top of it, ATR- and size-dependent slippage,
> gap-through stops, per-lot commission both sides, swap past rollover, 250 ms latency
> stress-tested at 500 ms. H-005 conditions (i)–(iii) apply and a run violating any of
> them is **VOID**, not a negative result.
>
> Both arms enter at the same times, one round turn per decision, at the same size.
> Spread and commission are therefore identical across arms and cancel in the
> *difference*, which makes the primary metric largely insensitive to the exact floor.
> **It does not cancel completely.** Swap is direction-asymmetric on gold, and gap-through
> severity differs by direction. The run reports realised cost per arm side by side; if
> they differ materially the invariance argument is void and must not be repeated in the
> writeup.
>
> H-005 (ii) is satisfied by reporting the breakeven spread of the **signal arm's own
> absolute expectancy**. The paired difference has no meaningful breakeven spread under
> the invariance above, and reporting one as unbounded would be an artefact of the
> pairing rather than a fact about the edge.

**F — The test**

> Primary, unchanged in substance: difference in expectancy per trade, bootstrap
> `p < 0.05`, **one-sided** — the claim is directional.
>
> Paired statistic: `d_i = pnl_signal,i − mean_s pnl_random,s,i` over the 1,364 decisions;
> test `mean(d) > 0`.
>
> | | value |
> |---|---|
> | resampling | stationary bootstrap (Politis–Romano) over the decision sequence |
> | expected block length | **10 decisions** |
> | resamples | 10,000 |
> | seed | 1337 (`REPRODUCIBILITY.md` §3, `bootstrap`) |
>
> Block length is a registered degree of freedom, not a measurement. Decisions are already
> non-overlapping so label-window dependence is zero, and what remains is regime
> persistence. **Sensitivity is reported at block length 1 and 25 alongside the primary
> figure** — reported, never selected from, exactly as with K-1's ε.
>
> Secondary, reported but explicitly not part of the verdict: the rank of the signal arm's
> expectancy within the 30 random arms. Same treatment as H-001's unshuffled control — a
> number worth carrying forward, not a second test.

**G — A contradiction inside the constitution, resolved conservatively**

> The original interpretation below said PASS means "proceed to build the agent panel".
> `EVALUATION.md` §2 says the ladder must be beaten **in order**, and the agent panel is
> rung 5. Rungs 2 (always-long), 3 (buy-and-hold, risk-parity sized) and 4 (single moving-
> average crossover) sit between. As written, H-003's PASS action skipped three rungs of a
> ladder whose entire premise is that skipping is what produces false confidence.
>
> Under `CLAUDE.md`'s conflict order a registered hypothesis outranks this, so the
> contradiction is resolved by **tightening H-003, not by reinterpreting §2**: PASS now
> licenses rung 2 and nothing further. Narrowing what a result licenses is always
> permitted — it is the same asymmetry as H-005's spread floor, which may be raised freely
> and lowered only through a new ID.
>
> Rungs 2–4 are **not** measured in this run. They are cheap once the engine exists, but
> rung 4 needs a fast/slow pair and rungs 2–3 need an equity-curve comparison rather than a
> per-decision one; inventing those constants here would smuggle three unregistered
> choices into an amendment. They get their own hypothesis ID when they are run. What this
> entry does fix is that the engine must be **able** to run them without new engine work —
> see §I.

**H — Registered researcher degrees of freedom**

> Every constant this entry introduces, with its value, in one place. None may change after
> the run without a new hypothesis ID.
>
> | constant | value | class |
> |---|---|---|
> | `SIGNAL_THRESHOLD` τ | 0.0 | minimum-DoF choice (§B) |
> | `STOP_ATR_MULT` | 1.5 | judgement |
> | `TARGET_ATR_MULT` | 1.5 | judgement, constrained to equal the stop (§D) |
> | `MAX_HOLD_BARS` | 24 | derived from the registered label horizon |
> | `ENTRY_FILL` | open of `T+1` | forced by §10 latency |
> | `INTRABAR_RESOLUTION` | stop-first | forced by §10 pessimism |
> | `BOOTSTRAP_BLOCK` | 10 decisions | judgement; sensitivity at 1 and 25 reported |
> | `N_RANDOM_SEEDS` | 30, enumerated `0…29` | matches H-001 |
> | `SPREAD_FLOOR_POINTS` | 75 | H-005; may be raised, never lowered |
>
> **Guardrail.** Re-running H-003 under different constants and reporting whichever passes
> is `EVALUATION.md` §9 — as many hypotheses as configurations tried — and `RESEARCH.md`
> §5.2. A second configuration is a second ID and a second draw against `N_claims`.

**I — What the engine must implement to satisfy this entry**

> The scope, registered rather than left to be discovered while writing it. `CLAUDE.md`
> Build Order step 3.
>
> 1. **Position lifecycle** — one function taking a direction, producing entry fill, stop,
>    target, time exit, gap-through resolution and the pessimistic intrabar rule. Both arms
>    and every later rung route through it.
> 2. **Cost model** as §E, versioned and hashed into the run manifest (`cost_model_version`,
>    `REPRODUCIBILITY.md` §5), with the H-005 deviation notice emitted by the manifest
>    writer rather than by the caller.
> 3. **Build-enforced H-005 (i)–(iii)** — the floor as a module constant with a test
>    asserting it has not been reduced, in the same pattern as the K-1 sensitivity guard.
> 4. **Decision log** per `REPRODUCIBILITY.md` §7, written for both arms, with
>    `decision_method: logistic` and `random` respectively. LLM fields null — there is no
>    model in this path.
> 5. **Breakeven-spread solver** — the spread floor at which the signal arm's expectancy
>    reaches zero, required by H-005 (ii) for every edge claim.
> 6. **Direction-source injection** so rungs 2–4 and, later, an agent, are new direction
>    sources rather than new engines. This is what makes §G's deferral cheap.
> 7. **Doubling test (K-5)** — every cost doubled, re-run, reported.
>
> Not in scope for H-003 and not blocking it: DSR (K-7) and `N_eff` (§6). DSR corrects a
> *Sharpe* for selection and H-003's metric is expectancy difference; `N_eff` measures
> agreement among agents and there are no agents. Both are required before any claim that
> reports a Sharpe or an agent panel, and neither is a reason to delay this run.

---

**Amended again 2026-07-28, still before any run: the constants the engine introduced**

> The first amendment specified H-003 before the engine existed, which was the right
> order. Building it then introduced constants the specification could not have named —
> a slippage coefficient, a commission, two swap rates — because a cost model has to be
> written before anyone knows what is in it. **Those constants are now in the evaluation
> path and they were not registered.** This block registers them, before the run and
> before any of them has produced a number.
>
> Two of the three findings below came out of building the thing, which is the argument
> for building it before running rather than after registering.

**J — The trade window is one bar longer than the label window**

> §D fills at the open of `T+1` and times out after 24 bars, so a decision at `T` touches
> bars through **`T+25`**. H-001's eligibility mask validates `[T, T+24]`. The 25th bar is
> outside the registered mask, and a decision whose 25th bar is invalid would be simulated
> straight across a hole and produce an ordinary-looking number.
>
> Two further eligibility conditions therefore apply, and are registered here:
>
> 1. **`atr_14` valid and finite at the decision bar.** The risk geometry reads a feature
>    the design matrix does not contain (§A), so its validity is a new condition rather
>    than one already covered. An ATR averaged across an unexplained gap sets a stop
>    distance that looks perfectly ordinary.
> 2. **Every bar in `[T, T+25]` valid.** The traded window, not the labelled one.
>
> `[MEASURED]` `scripts/report_h003_setup.py` over the H-001 snapshot:
>
> | eligibility | eligible bars | decisions |
> |---|---|---|
> | H-001 registered mask | 64,886 | **1,364** |
> | + `atr_14` valid and finite | 64,886 | **1,364** |
> | + trade window `[T, T+25]` valid | 64,879 | **1,364** |
>
> **The decision count does not change.** Seven bars lose trade-window validity and none
> of them lands on a grid point. K-6 still clears at 9.1x. That the answer is "no change"
> is what makes it worth recording: had it been checked after the run instead, the same
> arithmetic would have been indistinguishable from a rationalisation.

**K — The realised-cost comparison is a first-class output, not a caveat**

> §E argued a partial cost invariance. Building the engine showed the argument was
> **weaker than §E stated**, and the correction is recorded rather than quietly absorbed:
>
> | component | identical across arms? | why |
> |---|---|---|
> | entry half-spread | yes | same bar, same multiplier |
> | entry slippage, entry latency | yes | same ATR, same lots |
> | commission | yes | same lots, two sides always |
> | **exit half-spread** | **no** | the arms exit on different bars, and the multiplier is a property of the bar |
> | **exit latency** | **no** | a limit target pays none; a stop or time exit does |
> | **swap** | **no** | direction-asymmetric rates *and* different holding lengths |
> | **gap-through** | **no** | a long and a short gap through different levels |
>
> §E said "spread and commission are therefore identical across arms". Only *entry*
> spread and commission are. Four components provably differ, so the honest question is
> not whether the costs match but whether the residual divergence is small next to the
> effect being measured.
>
> **Registered rule, with a consequence rather than a caveat.** The run reports realised
> cost per arm per component, in R, as a first-class section. Let
> `divergence = |total_cost_signal - total_cost_control|` per decision and `effect` the
> measured expectancy difference. Then:
>
> - `divergence / |effect| <= 0.10` → the floor-insensitivity claim may be made.
> - `divergence / |effect| > 0.10` → **the claim is void for that run.** The primary
>   metric *is* a function of H-005's spread floor, the result must say so in the finding
>   rather than in a footnote, and the **breakeven spread of the difference** is required
>   alongside the signal arm's own.
> - A component marked identical-by-construction that is *not* identical → the comparison
>   is not interpretable at all. That is a defect in the grid or the sizing, not a cost
>   finding, and the run halts on it.
>
> `COST_DIVERGENCE_TOLERANCE = 0.10` is a judgement and is registered as one.

**L — Every cost constant, registered**

> The §10 model needs numbers §10 does not supply. Each is marked by what fixes it:
> **forced** by a rule with no freedom in it, **derived** from something already
> registered, or **judgement** — a choice someone made, which is the only category that
> can be gamed and therefore the only one that matters here.
>
> | constant | value | class |
> |---|---|---|
> | `SPREAD_FLOOR_POINTS` | 75 points | forced — H-005 (i), raisable only |
> | `WEEKLY_OPEN_MULTIPLIER` | 3x | forced — §10's stated range, low end |
> | `SCHEDULED_NEWS_MULTIPLIER` | 10x | forced — §10's stated range, high end |
> | `WEEKLY_OPEN_BARS` | 3 | judgement |
> | `SLIPPAGE_ATR_COEFF` | 0.05 of ATR per side | judgement |
> | slippage size scaling | square root | judgement — standard market-impact form |
> | `COMMISSION_POINTS_PER_LOT_PER_SIDE` | 3.5 | judgement |
> | `SWAP_LONG_POINTS_PER_LOT_PER_NIGHT` | 20, charged | judgement |
> | `SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT` | 8, charged | judgement |
> | `LATENCY_DEFAULT_SECONDS` | 0.25 | forced — §10 |
> | `LATENCY_ATR_COEFF_PER_SECOND` | 0.02 | judgement, deliberately small |
> | `RISK_PER_TRADE` | 100 currency units | derived — the unit R is measured in |
> | `COST_DIVERGENCE_TOLERANCE` | 0.10 | judgement (§K) |
>
> **Swap is charged in both directions.** A credit is an optimistic assumption about a
> rate this project has never observed, and §10 does not permit one.
>
> **The latency coefficient is small on purpose.** At H1 resolution a 250 ms delay is not
> separately observable, and the material latency assumption is not this term at all — it
> is the registered rule that a signal on bar `T`'s close fills at bar `T+1`'s open, a
> delay 14,400x longer. A large coefficient here would be double-counting dressed as
> conservatism.

**M — What the event model does not reach, as a number**

> §10 says the spread widens 3-10x "around scheduled news and at the weekly open". This
> project has no economic calendar, so the implemented event set is the weekly open and
> the payrolls hour, and nothing else.
>
> `[MEASURED]`, same run: **1,728 weekly-open bars and 125 payrolls-hour bars, 2.83% of
> the series.** The other 97.17% is priced at the flat floor, every non-payrolls scheduled
> release included.
>
> That error is **optimistic**, and its direction is stated rather than argued away. Three
> things bound it: the floor is already 5x the observed demo quote and 2.5-3.6x the
> broker's own recorded median; the coverage share is printed in every run; and K-5 plus
> the breakeven spread say how wrong the assumption can be before the result changes sign.
> None of them is an economic calendar. When one exists, this set widens through a new
> hypothesis.

**N — Rung extensibility is build-enforced**

> §I requirement 6 said rungs 2-4 must be new direction sources rather than new engines.
> That is a testable property and it is now tested: `tests/backtest/test_rungs.py`
> implements all three §2 rungs **against the protocol, from the test module**, and runs
> them through the unmodified engine. If a rung could only be built by editing the engine,
> that file would not import.
>
> It also guards the other direction. `test_no_rung_has_been_smuggled_into_the_evaluation_path`
> fails if any of those three appears in `src/backtest/direction.py`, because a rung in
> the evaluation path is a fast/slow pair or a sizing rule nobody registered. The failure
> message is the registration conversation.
>
> Rung 3 is the one that shaped the design: buy-and-hold has no protective orders, so the
> lifecycle takes `float | None` stop and target multipliers rather than a large number
> standing in for "off". Had rungs 2-4 been deferred without this test, that would have
> been discovered when they were registered, and by then changing the engine would mean
> re-running everything built on it.

**Dataset & window**

> Derived snapshot `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6`,
> 65,395 in-window bars, 64,886 eligible, walk-forward, `FIRST_TEST_FRACTION = 0.50`,
> 5 folds — the geometry H-001 certified. Sealed holdout untouched.

**Sample size expected**

> 1,364 pooled decisions, 272–273 per fold. K-6 cleared by 9.1× pooled and 1.8× per fold,
> known before the run (§B).

**What a PASS does not establish**

> - **Not profitability.** The metric is a difference against random entry. A PASS with
>   negative absolute expectancy says the signal carries directional information the
>   geometry does not — it does not say the system makes money, and the writeup may not
>   imply it.
> - **Tier 2 at best** under `RESEARCH.md`, never Tier 1, while H-005 is open.
> - **Only rung 1.** See §G.
> - R-001 is untouched: no session-relative feature is in the signal. The fold *geometry*
>   still rests on the era declaration, which remains externally unconfirmed.

**Pre-committed interpretation** *(amended 2026-07-28 — PASS narrowed, see §G)*
> - PASS: the signal contains information the risk geometry does not. **Proceed to rung 2
>   of `EVALUATION.md` §2.** Not to the agent panel — rungs 2, 3 and 4 stand between.
> - FAIL: **K-4.** The architecture is not the problem — the signal is. Do not add agents;
>   adding agents to a signal with no information produces a more expensive way to be
>   wrong. Return to feature research.
> - AMBIGUOUS (the one-sided bootstrap CI straddles zero): **REJECT.** §3's default, and
>   the default is not overridden by a favourable point estimate.

--- RUN ---

- **Run manifest:** `runs/13ae20a1-76b6-402e-b256-3e4f7dad14bd.json`
  sha256 `53cde12e6b0fe3bf13e24270d1f0978e4bec03836922c5099234e467ca5ebed5`
- **run_id:** `13ae20a1-76b6-402e-b256-3e4f7dad14bd`
- **Executed:** 2026-07-28, commit `33ca731`, `git_dirty: false`
- **Registration precedes the run:** §A–§I committed `a617a29` (merged `293c150`),
  §J–§N committed `574677f` (merged `cf3fb28`). Both predate the run commit.
- **Data:** derived snapshot
  `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6`,
  1,364 decisions, K-6 cleared at 9.1x.
- **Cost model:** `ff16183e7684e0fc…`, H-005 deviation notice carried in the manifest.
- **Verdict:** **ACCEPTED — K-4 does not trip.**

**The primary test**

> | block | mean difference (R) | 95% CI | one-sided p |
> |---|---|---|---|
> | **10 (registered)** | **+0.060398** | **[+0.005120, +0.117878]** | **0.0204** |
> | 1 (sensitivity) | +0.060398 | [+0.008934, +0.111278] | 0.0109 |
> | 25 (sensitivity) | +0.060398 | [−0.001503, +0.122639] | 0.0288 |
>
> Signal expectancy −0.096292 R, control mean −0.156689 R over 30 seeds
> (min −0.204602, max −0.099200). **Zero of thirty control arms did as well as the
> signal.** Stationary bootstrap, 10,000 resamples, seed 1337.
>
> **At block 25 the two-sided 95% interval includes zero.** The one-sided p still
> clears 0.05, and the two are consistent — a one-sided p just under 0.05 corresponds
> to a two-sided interval that barely touches zero — but the verdict rests on the
> registered block and that is worth stating rather than reporting only the three
> p-values.

**§9 multiple-testing correction — the number this turns on**

> Benjamini–Hochberg across `N_claims = 2` puts the critical value for the most
> significant claim at `0.05 x 1/2 = 0.025`.
>
> - block 10 (registered): **p = 0.0204 ≤ 0.025 — survives**, by 0.0046.
> - block 1: p = 0.0109 — survives.
> - block 25: p = 0.0288 **> 0.025 — would not survive**.
>
> The result clears §9 at the registered block length and would not clear it at the
> upper end of its own registered sensitivity range. That is the single tightest
> margin in this run and it is recorded as such.

**Per fold, alongside pooled**

> | fold | n | signal R | control R | difference R | test era |
> |---|---|---|---|---|---|
> | 0 | 273 | +0.008234 | −0.200376 | **+0.208609** | 2017-10-07 |
> | 1 | 273 | −0.113504 | −0.221234 | +0.107730 | straddles |
> | 2 | 273 | −0.144524 | −0.204437 | +0.059913 | 2022-10-21 |
> | 3 | 273 | −0.195886 | −0.102641 | **−0.093245** | 2022-10-21 |
> | 4 | 272 | −0.035555 | −0.054385 | +0.018830 | 2022-10-21 |
> | pooled | 1,364 | −0.096292 | −0.156689 | +0.060398 | — |
>
> **The effect is not uniform and one fold reverses it.** It is largest in fold 0,
> declines monotonically through fold 3, and fold 3 is negative. Folds 2, 3 and 4 test
> entirely inside the 2022-10-21 era on training pools that are majority pre-2022 —
> the condition H-006's era term exists to make visible, and it is now visible in a
> result rather than only in the geometry.

**Realised cost per arm, per decision, in R**

> | component | signal | control | divergence |
> |---|---|---|---|
> | spread | 0.101342 | 0.101334 | 0.000008 |
> | slippage | 0.021793 | 0.021793 | 0.000000 |
> | latency | 0.005059 | 0.005163 | 0.000104 |
> | commission | 0.001121 | 0.001121 | 0.000000 (identical by construction) |
> | swap | 0.000738 | 0.000672 | 0.000067 |
> | gap-through | 0.002719 | 0.002622 | (diagnostic, already inside gross) |
> | **total** | **0.130053** | **0.130082** | **0.000030** |
>
> **Cost invariance holds.** Divergence is 0.05% of the measured effect, far inside the
> registered 10% tolerance, and no identical-by-construction component moved. The
> floor-insensitivity claim of §E may be made for this run.

**Breakeven spread**

> - **Signal arm, absolute expectancy: there is none.** Expectancy is **−0.006063 R at
>   a spread floor of zero.** The signal arm does not make money at any cost
>   assumption, including no costs at all.
> - **Paired difference: 1,447.3 points**, bracketed to within 3.9 — 19x the registered
>   75-point floor. Reported although invariance holds, because a number is more useful
>   than the argument it replaces.

**K-5 — every cost doubled**

> Difference **+0.067853 R**, 95% CI [+0.013624, +0.123120], p = 0.0078. The difference
> does not disappear; it grows slightly, because doubling the spread moves the
> executable price and therefore which bar a position exits on. **K-5 does not trip.**

**What this result does not say, stated at the same volume as what it does**

> 1. **The signal arm loses money.** −0.096292 R per decision, and −0.006063 R even at
>    zero spread. It loses *less* than random entry, which is the entire content of the
>    claim. Nothing here is a profitability finding.
> 2. **The leading alternative explanation is long bias, and this run cannot exclude
>    it.** The signal went long 767 times and short 597 — **56.2% long** against the
>    control's 50% by construction. Gold has a secular uptrend over this window. That
>    confound is exactly what `EVALUATION.md` §2 rung 2 isolates, and rung 2 has not
>    been run. It is not run here: §G deferred rungs 2–4 to their own hypothesis ID
>    precisely so a confound could not be tested with an unregistered arm inside the run
>    it threatens.
> 3. **A negative-BSS model beat random entry directionally.** H-001's unshuffled
>    control measured BSS −0.006766 for this combiner. There is no contradiction — the
>    sign of `p − 0.5` can carry information while the probability is badly calibrated —
>    but the pairing should be read as a caution about the combiner, not as
>    corroboration.
> 4. **Tier 2 at best** under `RESEARCH.md` while H-005 is open, and the event model
>    reaches 2.83% of bars (§M). Every non-payrolls scheduled release is priced at the
>    flat floor, an optimistic error that K-5 and the breakeven spread bound rather than
>    remove.

**Judgement-constant sensitivity, since the §9 margin is thin**

> Seven of the nine judgement constants (§L) are cost constants, and this run measures
> that the verdict does not turn on any of them: total cost divergence between the arms
> is 0.000030 R against an effect of 0.060398 R, and the difference's breakeven spread
> is 19x the floor. Errors in slippage, commission, swap or the latency coefficient
> cannot move it.
>
> The two that are not measured by this run:
>
> - **The 1.5x ATR stop and target.** Both arms share it, so it does not bias the
>   comparison — but it fixes the payoff shape of every decision, and the *magnitude* of
>   the difference is a function of it. This run says nothing about what the difference
>   would be at 1.0x or 2.5x. It is the one judgement constant the verdict could turn
>   on, and it is unmeasured.
> - **The bootstrap block length** is measured across its own registered range and the
>   verdict holds at 1, 10 and 25 against α = 0.05 — but not against the §9-corrected
>   0.025 at block 25. See above.

**Pre-committed action taken**

> PASS. **Proceed to `EVALUATION.md` §2 rung 2** — always-long — which is also the test
> of this result's leading confound. Not to rungs 3–5, and not to the agent panel.

**2026-07-28, after H-007 — the directional reading is withdrawn**

> Appended, not edited: §2 forbids changing an entry after its run, and nothing above this
> line is altered. The run happened as recorded and its arithmetic is unchanged.
>
> **What is withdrawn is the interpretation.** H-007 ran rung 2 on the same 1,364
> decisions with the same geometry and measured always-long at −0.096150 R against the
> signal's −0.096292 R — a difference of **−0.000141 R at `p = 0.5041`**. The leading
> confound this entry named in its own "what this does not say" section turned out to be
> the whole of the effect.
>
> Two consequences, both recorded here because a reader arriving at this entry must not
> leave it with the wrong impression:
>
> 1. **The +0.060398 R against random entry is a long bias.** It is not evidence that the
>    signal carries directional information. The verdict "K-4 does not trip" stands as a
>    statement about what was measured; it no longer supports the reading placed on it.
> 2. **It no longer clears §9.** `N_claims = 3` and H-007 returned `p = 0.5041 > 0.0333`,
>    so Benjamini–Hochberg rejects nothing in the family. The contingency was registered
>    before H-007 ran and resolved against.
>
> The `Status: ACCEPTED` line above is left alone deliberately. Rewriting it would make
> the registry a record of what is currently believed rather than of what was done, and
> the second is the only one of the two that is auditable.

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

### H-005 — Registered deviation from `EVALUATION.md` §10: spread is not calibratable

- **Registered:** 2026-07-27 11:40 UTC
- **Class:** gate — does not count toward `N_claims`
- **Status:** REGISTERED

**What this is**

> Not an edge claim. It is the registration of a deviation from a locked document, so that
> the deviation is a decision with a threshold and an exit condition rather than an
> omission discovered later. `RESEARCH.md` §7 requires a hypothesis for any edit that
> "could change whether a past or future run counts as a pass." Running the backtest with
> a cost model that does not satisfy §10 is exactly that, whether or not §10's text is
> touched.

**The deviation**

> `EVALUATION.md` §10 specifies spread as "session-dependent + event multiplier. Widens
> 3–10× around scheduled news and at the weekly open. **Never a constant.**"
>
> That model cannot be built. It requires a historical bid/ask series, and the probe
> establishes that no such series exists for this feed:
>
> - Genuine bid/ask ticks begin 2026-03-02, ~0.40 years back. The usable evaluation window
>   is **10.87 years** of dense H1 history (2015-09-11 to 2026-07-24, measured). Tick
>   coverage is ~3.7% of it.
> - The `spread` field on H1 bars is not a substitute. It is the spread recorded at bar
>   close, not the spread that would have been paid on a fill, and the probe measures its
>   coverage stepping from 0.0% (2015 and earlier) to 95.7% (2016) — the broker began
>   recording it then. Bars before that carry a zero that means *unrecorded*, and
>   `DATA_CONTRACT.md` §6 forbids treating a missing value as a measured one.
> - Coverage never reaches 100% even after 2016 — it runs 95.7% to 99.8% by year. So
>   between 0.2% and 4.3% of bars in the covered era also carry an unrecorded zero, and
>   they are **not** distinguishable from a genuine zero spread by value alone. Ingestion
>   maps every zero in this field to `None`, in both eras, for the same §6 reason.
> - The one spread that *is* observable is a demo quote. It reads 15 points with
>   `median == p95 == 15.0` across a full sampled day, on a symbol whose `spread_float`
>   flag is `True`. A floating-spread symbol showing zero variation over an entire day is
>   not reporting the market; it is reporting a demo server's fixed quote.
>
> So §10's spread row is unsatisfiable for the historical period, and it will stay
> unsatisfiable until the forward capture in `scripts/capture_ticks.py` has accumulated a
> real series.

**Substitute — what is used instead**

> A **pessimistic constant floor**, with §10's structure preserved above it:
>
> | Component | Substitute |
> |---|---|
> | Spread base | Constant floor at `INFLATION × observed_demo_spread` = **5 × 15 = 75 points = $0.75/oz**, one full spread per round turn, **$75 per 100 oz lot**. |
> | Session / event multiplier | **Unchanged from §10.** The 3–10× widening at news and the weekly open is applied *on top of the floor*, not on top of a calibrated base. |
> | Slippage, stop gap-through, commission, swap, latency | **Unchanged from §10.** |
>
> The deviation is confined to the base being a constant. Everything else in §10 stands.
>
> This is still a deviation and is registered as one: §10 says "never a constant" and this
> is a constant. The prohibition exists to forbid *optimistic* constants — a flat spread
> chosen because it is convenient understates cost in exactly the conditions where trades
> are most likely to be triggered. The substitute inverts that error's sign but does not
> make the deviation disappear.

**The inflation factor, and the argument for it**

> **×5, giving a 75-point floor.** The argument, stated as an argument and not as a
> measurement:
>
> 1. **The observed spread is a lower bound on the true one, and the direction is known.**
>    A demo server does not model liquidity. Its quote cannot be wider than the live one in
>    any systematic way, and it is routinely narrower. There is no scenario in which 15
>    points overstates what would have been paid.
> 2. **15 points is very likely the most optimistic spread in the entire 18-year span.**
>    The history covers 2008–09, gold's 2011 run, the April 2013 crash and March 2020. Gold
>    spreads in those windows were multiples of calm-market spreads, and gold was a thinner
>    retail product for most of the early history. A floor set at the single most favourable
>    observation available would be the definition of an optimistic assumption.
> 3. **Retail gold spreads are commonly 20–35 points in calm conditions** at brokers of this
>    type. A floor of 75 points sits above that band rather than inside it, which is the
>    point: it is chosen to be uncomfortable.
>
> **Supporting evidence measured after registration (2026-07-27 probe run).** The `spread`
> field is not a payable spread and is barred as a cost input, but it is a measurement of
> *something*, and what it measures bounds how wrong the demo constant is. By year:
>
> | | points | $/oz | vs the 15-point demo constant |
> |---|---|---|---|
> | demo quote, flat all day | 15 | $0.15 | — |
> | recorded median, 2016–2023 | 21–30 | $0.21–0.30 | **1.4–2.0× wider** |
> | recorded median, 2024–2026 | 10–15 | $0.10–0.15 | comparable |
> | recorded max, 2020 (COVID March) | **700** | **$7.00** | **47× wider** |
> | recorded max, typical year | 35–57 | $0.35–0.57 | 2.3–3.8× |
>
> Three things follow, and none of them were available when the factor was chosen:
>
> 1. **The demo constant is not merely optimistic, it is below the broker's own recorded
>    spread for the majority of the evaluation window.** In 2016–2023 the recorded median
>    is 1.4–2.0× the demo quote. A cost model anchored on 15 points would have understated
>    even the non-payable recorded figure.
> 2. **The 75-point floor sits 2.5–3.6× above the recorded median.** That is the margin
>    intended: comfortably outside the calm-market range, not inside it.
> 3. **The floor composed with §10's event multiplier reproduces the observed crisis
>    peak.** 75 × 10 = 750 points against a measured 2020 maximum of 700. That the
>    pessimistic ceiling lands within 7% of the worst spread the broker ever recorded is
>    not a derivation — the two quantities are not the same kind of thing — but it is the
>    difference between a multiplier chosen in a vacuum and one whose implied worst case
>    is the right order of magnitude. It also settles that the constant floor **must**
>    keep §10's multiplier on top: the floor alone is 11% of the crisis peak.
>
> The 2020 figure also disposes of any argument that a flat spread is adequate. A feed
> whose recorded spread reaches 47× its calm-market value has an event structure, and a
> constant model cannot represent it in either direction.
>
> **Counter-argument, recorded because it is correct.** A multiplier not derived from
> measurement is not evidence, and no amount of prose makes ×5 a fact. It is a choice
> between two errors. A factor set too high kills real edges (Type II). A factor set too
> low admits false ones (Type I). `RESEARCH.md` §0 puts the burden of proof on the
> feature, never on the skeptic, so the choice errs deliberately toward Type II. That is a
> stated preference, not a derivation, and it is registered here — before any backtest
> exists — precisely so it cannot be revised downward after seeing a result it kills.

**Primary metric & threshold — what makes this a gate rather than an assumption**

> The factor is not the deliverable. **Breakeven spread is.**
>
> Every result reported while this gate is open must state the **breakeven spread**: the
> constant spread floor, in points, at which the measured edge reaches zero. That converts
> the unknown from an argument into a measured quantity — instead of debating whether ×5
> is right, the reader is told the edge survives up to *N* points and can apply their own
> judgement about what the live spread was.
>
> | # | Condition | Threshold |
> |---|---|---|
> | i | Default backtest spread floor | ≥ **75 points**. A run using less is **VOID**. |
> | ii | Breakeven spread reported alongside every edge claim | present, or the claim is void |
> | iii | Deviation notice carried in the run manifest of every run in the evaluation path | present, or the run is void |
>
> Any failure voids the run. It is not a K-code: `CLAUDE.md` Hard Rule 4 reserves K-codes
> for research-validity conditions in `EVALUATION.md` §1, and this is a registered
> deviation, not a kill criterion. §1 is unchanged and stays unchanged.

**What K-5 can and cannot establish under this substitute**

> Recorded verbatim, because it is the whole reason this entry exists:
>
> > **Passing K-5 rules out an edge that is marginal at assumed costs. It does not rule out
> > an edge that exists only because historical costs are understated.**
>
> K-5 doubles the *assumed* cost. If the assumption is wrong by more than 2×, doubling does
> not reach the truth — it stress-tests the neighbourhood of a wrong number. The inflation
> factor is what makes the assumption's error direction known; K-5 then tests robustness
> around it. Composed, the two give an effective stress of **10× the observed demo spread**
> (5× floor, doubled). That is the strongest statement available, and it is a statement
> about a bound, not about the market.

**Guardrail — what this must not become**

> The floor may be raised at any time without a new hypothesis; raising it is
> conservative and cannot manufacture an edge. **Lowering it requires a new hypothesis ID**,
> and if it is lowered after a result that the higher floor killed, that result is
> hypothesis laundering under `RESEARCH.md` §5.2 regardless of what justification
> accompanies it.

**Enforcement**

> The backtest engine does not exist yet (`CLAUDE.md` Build Order step 3), so there is
> currently nothing that can violate this. When it is built, conditions (i)–(iii) become
> build-enforced in the same pattern as the K-1 sensitivity guard: the floor as a module
> constant with a test asserting it has not been reduced, and the deviation notice emitted
> into the run manifest by the manifest writer rather than by the caller.

**Exit condition**

> This gate closes when the spread model can satisfy §10 as written. Two routes:
>
> - **(a) Forward capture matures.** `scripts/capture_ticks.py` accumulates genuine bid/ask
>   across at least one full annual cycle — enough to fit a session-dependent curve and to
>   observe the news and weekly-open widening §10 names. The §10 model is then built from
>   it and this substitute is retired **through a new hypothesis**, not by deleting this
>   entry.
> - **(b) A historical tick source is obtained** with genuine bid/ask covering the
>   evaluation window, and validated against the forward capture over their overlap. The
>   overlap check is not optional: a third-party tick series that disagrees with the
>   execution broker's own quotes is not a cost model for this broker.
>
> Until one of those closes it, **no result may be described as satisfying §10**, and every
> run in the evaluation path cites H-005.

**Pre-committed interpretation**

> - If a run satisfies (i)–(iii): the result stands, annotated as resting on a bounded cost
>   assumption rather than a calibrated one. It is admissible at `RESEARCH.md` Tier 2 at
>   best, never Tier 1, while this gate is open.
> - If a run violates any of (i)–(iii): the run is **VOID**. Re-run it correctly. A void
>   run is not a negative result and concludes nothing.
> - If the breakeven spread comes in *below* the observed demo spread of 15 points: there
>   is no edge at any plausible cost assumption, and the configuration is terminated
>   without waiting for the calibrated model.

--- OPEN ---

- **Closes via:** a new hypothesis under exit condition (a) or (b). Never by editing this
  entry.

### H-006 — The evaluation window is a declared boundary, not a truncation

- **Registered:** 2026-07-27 13:20 UTC
- **Class:** gate — does not count toward `N_claims`
- **Status:** REGISTERED

**What this is**

> The declaration of which span of history is admissible, made once, in advance, with the
> measurement that forced it. Not an edge claim.
>
> It exists because the alternative is worse than it looks. Nobody would consciously
> decide to drop ten years of history; what happens instead is that a feature needing 24
> bars silently returns `None` for every sparse day, the sparse days silently drop out of
> the design matrix, and the run reports `n` without anyone noticing that `n` came from a
> different span than the one described in the writeup. That is a truncation nobody chose
> and nobody can audit. Registering the boundary converts it into a decision with a
> number attached.

**The measurement that forces it**

> The feed advertises 18.38 years — 2008-03-11 to 2026-07-27, 67,362 H1 bars. That figure
> describes two different datasets stored in one series:
>
> | era | bars/day (median) | dense days | what it can support |
> |---|---|---|---|
> | 2008 → 2015-09 | **1** | 0 | nothing at H1 |
> | 2015-09 → 2026 | **23–24** | 2,785 | the full protocol |
>
> A day carrying one bar cannot produce a 24-bar label, an ATR, or a session feature. The
> sparse era is not low-quality data for these purposes — it is *absent* data with a
> timestamp. 2008–2014 contributes 1,780 bars total, fewer than a single dense month.
>
> Measured consequence: **2,785 dense days, 2,709 non-overlapping decisions at H=24, over
> 10.87 years.** That clears K-6 pooled, K-6 per fold at five folds, K-6 on a 20% sealed
> holdout, and spans 2022 with 1,614 dense days before and 1,171 after for `EVALUATION.md`
> §11's regime split. The protocol is runnable on the dense era alone. Nothing is lost by
> declaring the boundary except the illusion of an 18-year sample.

**Primary metric & threshold — the conditions this gate asserts**

> | # | Condition | Threshold |
> |---|---|---|
> | i | Every run in the evaluation path declares `window_start` and `window_end` in its manifest | present, or the run is **VOID** |
> | ii | `window_start` ≥ the measured sparse/dense boundary | else **VOID** |
> | iii | Every reported result states the window it used, in the same place it states `n` | present, or the claim is void |
> | iv | Bars outside the declared window are **absent from the loaded frame**, not filtered downstream | asserted by test |
>
> Condition (iv) is the one that does the work. Filtering late leaves a window that is
> whatever survived the last filter, which is the silent truncation this gate exists to
> prevent. Excluding at load time makes the window a property of the data, and a feature
> cannot quietly widen it.
>
> Any failure voids the run. Not a K-code — `CLAUDE.md` Hard Rule 4 reserves those for
> `EVALUATION.md` §1, which is unchanged.

**Where the boundary is — and the one thing still to confirm**

> The 2026-07-27 probe run reports **78 dense days in 2015** and a first dense day of
> **2015-09-11**. From 2015-09-11 to year end there are 80 weekdays; less Christmas and
> New Year closures, 78. The dense count matches the trading-day count for that span
> exactly, which is what a **clean cliff** looks like and not what a ramp looks like.
>
> That is consistent, not confirmed: 78 scattered dense days would produce the same total.
> The distinguishing measurement is the count of days from the **one-bar-a-day era**
> occurring *after* the first full day — zero for a cliff, non-zero for a ramp.
>
> **Amended 2026-07-27, second run.** The first version of that measurement reported a
> ramp running to the present day, and it was wrong twice over. Both defects are recorded
> because both would have set this window silently:
>
> 1. **Two populations were merged.** It split days at the dense threshold and called
>    everything below it "sparse", so ~20 ordinary **short trading days** — holiday
>    sessions carrying 16–19 bars, scattered through the dense era — were counted as
>    sparse-era days. The era therefore appeared never to end.
> 2. **The in-progress day set the boundary.** The probe runs mid-session, so the final
>    calendar day is short by construction. It became the "last sparse day", and the rule
>    "start after the last sparse day" would have set `window_start` to **tomorrow** — an
>    empty window, produced by a rule that reads as conservative.
>
> The corrected measurement uses three populations and drops the final day. This matters
> beyond the date, because it separates **two different exclusion mechanisms** that the
> merged version could not distinguish:
>
> | | mechanism | what it excludes |
> |---|---|---|
> | **the window** | `window_start`, applied at load | the one-bar-a-day era — a span with no data |
> | **per-day validity** | bar count on the day itself | short trading days — real sessions too short for a 24-bar label |
>
> A short holiday session inside the dense era is not an era question and must not move
> the window. It is excluded on its own merits, one day at a time, and the days around it
> are unaffected. Conflating the two is what produced the false ramp.
>
> **FROZEN 2026-07-27, third run: `window_start` = 2015-09-11.**
>
> The corrected measurement reports a clean cliff:
>
> | | |
> |---|---|
> | last one-bar-era day | **2015-09-09** |
> | first full day | **2015-09-11** |
> | one-bar-era days after the first full day | **0** |
> | short trading days inside the dense era | 19 (excluded per day, not by the window) |
>
> Zero is the number that decides it. The feed changes character exactly once, so a single
> date describes the boundary and no window opening at it can admit a day with no data.
> The 78-dense-days-in-2015 arithmetic that suggested this in the first run is now
> confirmed by the measurement that could have falsified it.
>
> `window_end` is the last complete day in the snapshot, never the in-progress day — the
> same rule that stopped the boundary computation from being set by a partial session.
>
> The gap census places a 10-bar hole at 2015-09-10 — the boundary day itself, half sparse
> and half dense. It is an artefact of the transition, not a defect, and it falls outside
> the window under either reading.

**Amended 2026-07-27, first full ingest: the window spans three session eras, and era
becomes an explicit term**

> This amendment adds a term. It does not move `window_start`, relax a condition, or
> change what the gate asserts.
>
> The first ingest of the complete H1 export showed something no fixture could have: the
> feed does not have one session structure across this window. It has three.
>
> `[MEASURED]` `scripts/report_session_eras.py` over
> `data/raw/GOLD-H1-20080311-20260727.csv`, counting bars per server day — a measurement
> that uses no conversion and no convention:
>
> | era | daily break | evidence |
> |---|---|---|
> | 2015-09-11 → 2017-10-06 | one hour, 17:00 New York | 23-bar days |
> | **2017-10-07 → 2022-10-20** | **none** | **936 Mon–Thu days carrying all 24 hours** |
> | 2022-10-21 → present | one hour, 17:00 New York | 23-bar days |
>
> The populations do not interleave. 1,079 Mon–Thu days carry 23 bars and 936 carry 24,
> excluding 152 days inside US/EU daylight-saving mismatch windows, which carry no era
> information because a whole server hour is absent on them in every era. Each boundary
> falls on a single weekend: the last 23-bar day before the middle era is Fri 2017-10-06
> and the first 24-bar day is Mon 2017-10-09; the last 24-bar day is Thu 2022-10-20 and
> the first 23-bar day is Fri 2022-10-21.
>
> **Both boundaries fall inside the registered window**, and that is why the term exists.
> This is not an observation about the feed's prehistory that the window already excludes
> — it is a change in what a "session" means, twice, in the middle of the span every
> result will be computed over.
>
> **Decision: keep the full window, add era as an explicit term.**
>
> | option | why not |
> |---|---|
> | restrict to one era | Discards data for no gain. The longest era is 936 days against 2,805; the K-6 headroom this gate was registered to establish would go with it. |
> | accept it silently | A session-relative feature would measure different things on either side of 2017-10-07 with **nothing recording that**. Silence is the failure mode this whole file exists to prevent — a result whose `n` came from a span nobody described. |
> | **era as a term** | Makes the difference visible and measurable rather than latent. If era has no effect, that is a finding with a number attached. If it does, the term is what shows it. |
>
> Restricting is the conservative-looking option and is the wrong one for the same reason
> §5.7 forbids disappearing inconvenient data: the era change is a property of the world
> and dropping two thirds of the window does not make it go away, it makes it unmeasurable.
>
> **What the term is**
>
> `session_era` is carried in the derived frame as a first-class column — the era's start
> date, one of three values, assigned from the frozen calendar rather than re-derived. It
> is a **property of the bar**, alongside `valid` and `in_window`, not a feature: nothing
> computes it, it is read off the declaration, and it changes only when the calendar
> changes.
>
> Any model fitted on this window either includes it or states that it does not and why.
> Any result reported over this window states the era composition of its sample in the
> same place it states `n`, by the same rule as condition (iii).
>
> **What this amendment does not settle**
>
> The era boundaries rest on evidence internal to this project. `REVIEW_ITEMS.md` **R-001**
> is open against them and blocks registering any session-relative feature until they are
> checked against a source outside this feed. The term is unblocked by that review: it
> records that the eras exist and lets their effect be measured, and if the review moves a
> boundary the term is recomputed. That is exactly the property a term has and a feature
> that bakes the dates in does not.

**Guardrail — what this must not become**

> `window_start` may be moved **later** without a new hypothesis; a shorter window is
> conservative and cannot manufacture an edge. Moving it **earlier requires a new
> hypothesis ID**, and moving it after seeing a result that the later start killed is
> hypothesis laundering under `RESEARCH.md` §5.2 whatever the accompanying justification.
>
> The era term is not a knob. **Dropping it after seeing a result it made worse is the
> same laundering**, and is harder to spot because removing a term reads as simplification
> rather than as selection. If a model is fitted without it, that is stated in the result
> alongside `n`, and the reason is stated too.
>
> The sparse era is **not deleted**. It stays in the raw snapshot, hashed and manifested
> like everything else. It is excluded from the evaluation window, which is a statement
> about admissibility, not about storage. `RESEARCH.md` §5.7 forbids disappearing
> inconvenient data and that applies to bars as much as to hypotheses.

**Pre-committed interpretation**

> - If the re-run confirms a cliff: `window_start` is frozen at the measured first dense
>   day and this gate moves to `STANDING`, enforced by the manifest writer and a test.
> - If the re-run shows a ramp: `window_start` is frozen at the day after the last sparse
>   day, by the rule above, and the ramp's extent is recorded here. Still `STANDING`.
> - If a future feed refresh moves the boundary: that is a new hypothesis, not an edit.
>   A boundary that moves silently is the failure this entry exists to prevent, and it
>   would be undetectable if the value were simply re-derived each run.

--- OPEN ---

- **Date frozen:** 2026-07-27, `window_start` = 2015-09-11, from a cliff measurement that
  reported zero one-bar-era days after the first full day.
- **Era term added:** 2026-07-27, on the first ingest of the full export. Three session
  eras, two boundaries inside the window. `session_era` is a derived-frame column.
- **Conditions (i)–(iv) are now build-enforced.** The loader and manifest writer exist:
  `src/data/loader.py` refuses out-of-window rows at load (iv), and
  `src/data/snapshot.py` writes `window_start` and `window_end` into every manifest (i),
  with `window_end` the last complete day and never the in-progress one. Condition (ii)
  holds by construction — the window comes from the frozen calendar. Condition (iii) is a
  reporting discipline and stays at review, like `REPRODUCIBILITY.md` §9.
- **Pending for `STANDING`:** nothing further in the data layer. The remaining gap is that
  no evaluation run exists yet to carry a manifest, so (i) and (iii) have no runs to be
  asserted against.
- **Blocked alongside:** `REVIEW_ITEMS.md` R-001, against the era boundaries. Open. It does
  not block this gate or the term; it blocks registering a session-relative feature.

---

### H-007 — Signal beats always-long (`EVALUATION.md` §2 rung 2)

- **Registered:** 2026-07-28 UTC
- **Executed:** 2026-07-28 on real market data
- **Class:** claim — counts toward `N_claims`
- **Status:** REJECTED — always-long matches the signal

**Claim**
> Over H-003's 1,364 decisions and H-003's risk geometry, the signal's expectancy per
> decision will exceed an always-long arm's at one-sided `p < 0.05`.

**Why this is the next thing and not something else**

> H-003 accepted: the signal beat random entry by +0.060398 R, `p = 0.0204`. It also went
> **long 767 times and short 597 — 56.2% long** — against a control that is 50% long by
> construction, on an instrument with a secular uptrend across the evaluation window.
>
> **A long bias produces exactly that difference with zero directional skill.** Rung 2 is
> the registered instrument for separating the two, and H-003 §G deferred it to its own
> ID precisely so the confound could not be tested with an unregistered arm inside the run
> it threatens. This is that ID.

**Registering this changes what H-003 currently means — stated before the run**

> `N_claims` goes 2 → 3. `EVALUATION.md` §9 applies Benjamini–Hochberg across the family,
> and the family is the registered claims, tested or not.
>
> Worked through, with H-004 untested and therefore carrying no p-value:
>
> | family | H-003's BH position |
> |---|---|
> | m = 2 (at H-003's decision point) | rank 1 critical `0.05 x 1/2 = 0.025`; **p = 0.0204 clears** |
> | m = 3, H-007 registered but not run | rank 1 critical `0.05 x 1/3 = 0.0167`; **p = 0.0204 does not clear** |
> | m = 3, H-007 returns `q` | BH is step-up: `k = 2` holds when `p(2) ≤ (2/3)(0.05) = 0.0333` |
>
> So: **H-003's acceptance is now contingent on this run returning `p ≤ 0.0333`.** If
> H-007 comes back above that, neither claim clears the correction and H-003's verdict
> does not survive the enlarged family.
>
> This is recorded here rather than by editing H-003 — §2 forbids editing an entry after
> its run — and it is recorded *before* H-007 executes so that it cannot be presented
> afterwards as a discovery. It is also the multiple-testing machinery doing exactly what
> it exists for: **registering another claim weakened an accepted one, visibly.**

**Change under test**
> One thing: the direction source. Always-long replaces the combiner. The decision grid,
> the risk geometry, the cost model, the eligibility mask and the bootstrap are H-003's,
> unchanged.

**The signal arm is H-003's, not a refit**

> The same probabilities, from the same per-fold combiner fits, over the same 1,364
> decisions. Refitting would introduce a degree of freedom between two runs that are
> supposed to differ in one thing.

**The control**
> `AlwaysLong` — `Direction.LONG` at every decision. Deterministic, so **one control arm,
> not thirty**: there is no seed to sweep. The paired statistic is
> `d_i = pnl_signal,i − pnl_always_long,i` over the 1,364 decisions.

**Primary metric & threshold**
> Difference in expectancy per decision, stationary bootstrap, **one-sided `p < 0.05`**,
> expected block **10**, 10,000 resamples, seed 1337. Sensitivity reported at block 1 and
> 25 — reported, never selected from. Identical to H-003 §F so the two are comparable.

**A cost divergence that is predictable in advance, and predicted here**

> Swap is direction-asymmetric: 20 points per lot per night long, 8 short. The signal is
> 56.2% long; always-long is 100% long. **The control will pay more swap than the signal,
> systematically, in the direction that favours the signal.**
>
> Order-of-magnitude estimate from H-003's measured signal swap of 0.000738 R:
> `0.000738 x 20 / (0.562 x 20 + 0.438 x 8) ≈ 0.0010 R`, a divergence near **0.00026 R**.
> That is 1.3% of an effect the size of 0.02 R and 13% of an effect the size of 0.002 R.
>
> H-003 §K's rule applies unchanged: above a 10% divergence share the floor-insensitivity
> claim is void, the result says so as a finding, and the breakeven spread of the
> difference becomes required. Given the estimate above, **this run is materially more
> likely to void it than H-003 was**, and that is registered now rather than explained
> later.

**Also reported, not part of the verdict**
> Always-long's own absolute expectancy; both arms' long share; per-fold results alongside
> pooled, given the era composition H-006 made visible and H-003's fold-3 reversal;
> realised cost per component per arm; K-5 doubling.

**Sample size expected**
> 1,364 decisions, unchanged. K-6 cleared at 9.1x. The multiple does not change the grid.

**Pre-committed interpretation**

> - **Always-long matches or beats the signal** (difference ≤ 0, or > 0 but not at
>   `p < 0.05`): **the H-003 difference is a long bias and carries no directional
>   information.** H-003's directional reading is withdrawn — the run stands as a record,
>   the interpretation does not. Halt the ladder. Return to feature research. Do not build
>   rung 3, and do not build an agent.
> - **The signal beats always-long at `p < 0.05`**: the difference survives its most
>   likely confound, and **rung 3 becomes the question**. Nothing beyond rung 3 is
>   licensed by this.
> - **AMBIGUOUS** (the one-sided bootstrap CI straddles zero): **REJECT.** §3's default,
>   not overridden by a favourable point estimate.
> - Whatever the outcome, report H-003's BH status under the resulting family (see above).

**Guardrail**
> Always-long has no parameters, which is the point — there is nothing here to tune. The
> risk geometry is H-003's and may not be varied inside this run; varying it is H-008,
> deliberately separate.

--- RUN ---

- **Run manifest:** `runs/ab8dfbcb-c48d-4f2e-ac30-5bd9a7e5c5de.json`
  sha256 `2f02739ab0a19cc3d6e3160917a53c16a8c91f693efedea63795b40056c82da9`
- **run_id:** `ab8dfbcb-c48d-4f2e-ac30-5bd9a7e5c5de`
- **Executed:** 2026-07-28, commit `6189945`, `git_dirty: false`
- **Data:** the H-003 snapshot and grid, 1,364 decisions, K-6 cleared at 9.1x.
- **Verdict:** **REJECTED. Always-long matches the signal.**

**The primary test**

> | arm | expectancy R | long | short | long % |
> |---|---|---|---|---|
> | signal | **−0.096292** | 767 | 597 | 56.2% |
> | always-long | **−0.096150** | 1,364 | 0 | 100.0% |
>
> | block | mean difference (R) | 95% CI | one-sided p |
> |---|---|---|---|
> | 1 (sensitivity) | −0.000141 | [−0.066149, +0.065493] | 0.4942 |
> | **10 (registered)** | **−0.000141** | **[−0.074192, +0.072810]** | **0.5041** |
> | 25 (sensitivity) | −0.000141 | [−0.078999, +0.078968] | 0.5053 |
>
> **The difference is −0.000141 R — negative, and two orders of magnitude smaller than
> H-003's +0.060398 R against random entry.** `p = 0.5041`: a coin flip. The sensitivity
> range does not move it. There is nothing here to interpret.

**It is worse than the net numbers show**

> Always-long paid **0.000727 R more per decision in costs** than the signal. Net, the
> signal is behind by 0.000141 R. **Gross, it is behind by 0.000868 R** — the cost
> divergence is the only thing holding the net difference near zero rather than below it.
>
> The arm that took no view at all, and paid more to do it, still finished ahead.

**Per fold, alongside pooled**

> | fold | n | signal R | always-long R | difference R | test era |
> |---|---|---|---|---|---|
> | 0 | 273 | +0.008234 | −0.174638 | **+0.182872** | 2017-10-07 |
> | 1 | 273 | −0.113504 | −0.279320 | +0.165816 | straddles |
> | 2 | 273 | −0.144524 | −0.048115 | −0.096409 | 2022-10-21 |
> | 3 | 273 | −0.195886 | +0.023129 | **−0.219015** | 2022-10-21 |
> | 4 | 272 | −0.035555 | −0.001460 | −0.034096 | 2022-10-21 |
> | pooled | 1,364 | −0.096292 | −0.096150 | **−0.000141** | — |
>
> The same shape H-003 showed against random entry, and now with the sign flipping in the
> middle: the signal is ahead in folds 0 and 1 and behind in 2, 3 and 4. **Whatever it
> had was in the pre-2022 period, and the pooled figure is two opposite regimes cancelling
> — not a stable small effect.**

**Realised cost per arm, per decision, in R**

> | component | signal | always-long | divergence |
> |---|---|---|---|
> | spread | 0.101342 | 0.101851 | **0.000509** |
> | slippage | 0.021793 | 0.021793 | 0.000000 |
> | latency | 0.005059 | 0.005056 | 0.000002 |
> | commission | 0.001121 | 0.001121 | 0.000000 (identical by construction) |
> | swap | 0.000738 | 0.000959 | **0.000221** |
> | **total** | **0.130053** | **0.130780** | **0.000727** |
>
> **The registered prediction, scored.** §H-007 predicted a swap divergence of
> **0.00026 R**; measured **0.000221 R** — right sign, right mechanism, right order,
> about 15% over.
>
> **The prediction was also incomplete, and that is the more useful half.** The dominant
> divergence was not swap but **spread, at 0.000509 R — 2.3x the swap term.** H-003 §K
> names exit half-spread as a component that cannot be identical across arms, because the
> arms exit on different bars and the event multiplier belongs to the bar. That mechanism
> was registered; what was not registered was that it would dominate. A prediction that
> names one term and misses the larger one is half right and is recorded as such.
>
> **Cost invariance: VOID.** Divergence is 514.5% of the measured effect. That ratio is
> not "five times too large" in any useful sense — the denominator is a difference
> indistinguishable from zero. The honest reading is **the arms' cost difference is larger
> than the effect being measured**, which is another way of saying there is no effect.

**Breakeven spread — and a defect in how it was first reported**

> **There is none.** The difference changes sign three times across the bracket:
>
> ```
> 0:+0.000550  250:+0.019471  500:-0.003999  750:-0.006078  1000:+0.002790
> 1250:-0.016436  1500:-0.010511  1750:-0.012971  2000:-0.003477
> ```
>
> This is what a quantity indistinguishable from zero looks like when the spread floor
> moves and reshuffles which bar each position exits on.
>
> **The first execution of this run reported "1,076.2 points, bracketed to within 3.9".**
> That was a real crossing and a meaningless number, stated with a precision the quantity
> does not have. `solve_breakeven_spread` bisected a non-monotone curve. It now probes a
> nine-point grid first and refuses when the sign changes more than once, with the samples
> in the message so a reader sees the oscillation rather than taking the refusal on trust
> (commit `6189945`, `tests/backtest/test_metrics.py`). The run above is the re-execution
> under the fixed solver; every other number is identical.
>
> The verdict never depended on it. It is recorded because a reporting instrument that
> manufactures false precision is a defect whether or not it changed a conclusion this
> time.

**K-5**

> Doubled costs: **+0.010961 R**, 95% CI [−0.060060, +0.081631], `p = 0.3853`. Not
> significant in either direction. Nothing to trip.

**§9 — what this does to H-003**

> `p = 0.5041 > 0.0333`. Under Benjamini–Hochberg at `N_claims = 3`, `k = 0`:
> **neither claim clears the correction.** H-003's `p = 0.0204` does not survive the
> enlarged family.
>
> This was registered before the run, with the threshold stated, precisely so it could not
> be presented afterwards as a discovery. It resolved the unfavourable way.

**Pre-committed action taken**

> **Always-long matched the signal. The H-003 difference is a long bias and carries no
> directional information.** H-003's directional reading is **withdrawn** — the run stands
> as a record, the interpretation does not.
>
> Halt the ladder. **Do not build rung 3. Do not build an agent.** Return to feature
> research.
>
> H-008 is not run: its own Order clause makes it conditional on this passing, and a
> robustness sweep of a retracted reading measures nothing.

---

### H-008 — The 1.5x ATR stop and target: is H-003's difference stable in it?

- **Registered:** 2026-07-28 UTC
- **Class:** gate — does not count toward `N_claims`
- **Status:** REGISTERED

**What this is, and why it is a gate rather than a claim**

> H-003 §L classified thirteen cost and geometry constants. Seven are cost constants and
> the run **measured** that the verdict does not turn on them: cost divergence 0.000030 R
> against a 0.060398 R effect, and a difference breakeven at 19x the spread floor.
>
> One was identified as the exception: **the 1.5x ATR stop and target.** Both arms share
> it, so it does not bias the comparison — but it fixes the payoff shape of every decision,
> and the *magnitude* of the difference is a function of it. H-003 measured nothing about
> it. This is the registration of that measurement.
>
> It is a **gate**, not a claim, and the distinction is load-bearing: a gate cannot
> manufacture a false positive about edge. This one is constructed so that it cannot —
> **the sweep can only weaken or corroborate an existing result, never select a better
> configuration.** See the guardrail.

**Why it is registered separately from H-007, and not folded into it**

> Rung 2 tests a confound. This tests robustness. Running them together would mix the two
> and leave any disagreement unattributable — a difference that moved could be the
> baseline or the geometry, and nothing in the output would say which.
>
> The stronger reason: a sweep run alongside a baseline test invites choosing the
> multiplier that makes the baseline test pass. That is `RESEARCH.md` §5.2 hypothesis
> laundering, and separating the runs is what makes it structurally unavailable rather
> than merely discouraged.

**The sweep — fixed before running**

> | `stop_atr_mult` = `target_atr_mult` | |
> |---|---|
> | 0.75 | half the registered value |
> | 1.00 | |
> | **1.50** | **the registered value, unchanged** |
> | 2.00 | |
> | 3.00 | double the registered value |
>
> Five values, bracketing 1.5 by a factor of two either way. **Stop and target stay equal
> at every point.** H-003 §D registers the symmetry because it is what makes the random
> control's gross expectancy zero by construction; breaking it would change what is being
> measured rather than how robustly it is measured.
>
> The values are fixed here, before any of them has produced a number. Adding a sixth
> after seeing the five is a new hypothesis.

**What is run at each point**
> H-003's run, entire: the same signal probabilities, the same 30 random control arms,
> the same decision grid, the same cost model, the same bootstrap at block 10. Only the
> multiple changes.

**A confound inside the sweep, named in advance**

> Position size is `R / (k x ATR)`, so a wider stop takes a smaller position. Cost in R is
> `cost_points / (k x ATR)` — **cost per R falls as `k` rises.** The difference will tend
> to grow with `k` for that reason alone, with no change in information content.
>
> The run therefore reports **realised cost in R at every swept point** beside the
> difference. A difference that rises exactly as cost falls is cost dilution and must not
> be read as robustness.

**Pass conditions — all must hold**

> | # | Condition |
> |---|---|
> | i | The difference is **positive at all five** multiples |
> | ii | At least **three of five** clear one-sided `p < 0.05` at the registered block |
> | iii | The cost-in-R series is reported beside the difference series at every point |
>
> Failure of (i) or (ii) means H-003's difference is a property of one payoff shape rather
> than of the signal, and H-003's directional reading is **withdrawn** on the same terms
> as an H-007 failure.

**Reported, and explicitly not a pass condition**

> Whether 1.5 is the argmax of the difference across the five. If it is, the run says so —
> "the registered value is the best of five, which is what a tuned constant looks like" —
> and that is a flag for a reader, not a verdict. Making it a failure would build a gate
> that fires one time in five by luck, and `REPRODUCIBILITY.md` §10 forbids a gate whose
> firing nobody can attribute in either direction.

**Guardrail — the reason this can be a gate at all**

> **`STOP_ATR_MULT` and `TARGET_ATR_MULT` remain 1.5 whatever the sweep shows.** This run
> cannot change them. Adopting a different multiple requires a new hypothesis ID and a
> fresh draw against `N_claims`, and doing it *because* the sweep favoured it is
> hypothesis laundering under `RESEARCH.md` §5.2 regardless of the reasoning attached.
>
> That guardrail is what makes the sweep incapable of manufacturing an edge, and therefore
> what makes it a gate.

**Pre-committed interpretation**

> - PASS: the H-003 difference is not an artefact of the payoff shape. Its directional
>   reading survives this axis. Says nothing about the long-bias confound — that is H-007.
> - FAIL: **withdraw H-003's directional reading.** The run stands as a record; the
>   interpretation does not. Return to feature research.
> - Either way, `1.5` stays registered.

**Order**
> H-007 first. If H-007 fails, H-003's directional reading is already withdrawn and this
> sweep measures the robustness of something that has been retracted — there is nothing
> left for it to be about. Run it only if H-007 passes.

**2026-07-28 — not run, and not to be run as things stand**

> H-007 was rejected: always-long matched the signal at `p = 0.5041`, and H-003's
> directional reading is withdrawn. The Order clause above is therefore active. This gate
> stays `REGISTERED` and unexecuted — the sweep values remain fixed at 0.75, 1.0, 1.5,
> 2.0, 3.0 for whenever there is a directional reading to test the robustness of.
>
> It is not marked `VOID`. Nothing about it was invalidated; its subject was.

<!-- H-009 onward -->
