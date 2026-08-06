# HYPOTHESES.md — Pre-Registration Registry

**Append-only. Nothing is ever deleted or edited after its run.**
**Version:** 1.0

---

## 0. Running Counters

> Updated on every merge. These three numbers gate the validity of every claim the project
> makes.

```
Registered (registry completeness) ... 12
  ├─ Accepted ....................... 2   H-001 (K-1, 2026-07-27)
  │                                       H-003 (K-4, 2026-07-28) — see note
  ├─ Rejected ....................... 4   H-007 (rung 2, 2026-07-28)
  │                                       H-009 (volatility, 2026-07-28)
  │                                       H-010 (capacity gate, 2026-07-28)
  │                                       H-012 (feature slice, 2026-07-28)
  ├─ Standing ....................... 1
  └─ In flight ...................... 5

N_claims (multiple-testing denom.) ... N = 6
  ├─ gates  (not counted) ........... 6   H-001, H-002, H-005, H-006, H-008, H-010
  └─ claims (counted) ............... 6   H-003, H-004, H-007, H-009, H-011, H-012

Holdout openings used ............... 0 / 3
FDR correction level ................ α = 0.05, Benjamini–Hochberg
BH rank-1 critical value ............ 0.05 × 1/6 = 0.00833
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

> **Second note on H-003, 2026-07-28 — registering H-009 changes §9 again, and could
> change it in H-003's favour.** `N_claims` moves 3 → 4, so the BH critical values become
> `0.0125, 0.025, 0.0375, 0.05`. Because BH is step-up, **if H-009 returns `p <= 0.025`
> the procedure rejects the two smallest `p`-values, which includes H-003 at `0.0204`.**
> H-003 would then clear `EVALUATION.md` §9 for the first time.
>
> That would change nothing about what H-003 means. Its directional reading was withdrawn
> on H-007's substantive grounds — always-long matched the signal at `p = 0.5041` — not on
> §9's. A volatility claim clearing a multiple-testing correction is not evidence about
> direction, and this note exists so the coupling is on the record *before* H-009 runs and
> cannot be presented afterwards as a rehabilitation. See H-009 §D.

> **It happened. 2026-07-28.** H-009 returned `p = 0.0150`. At `m = 4` the BH step-up finds
> `k = 2` and **rejects both nulls: H-003 clears `EVALUATION.md` §9 for the first time.**
>
> **H-003's directional reading remains withdrawn.** Nothing about H-007's measurement has
> changed. The clearance is a multiple-testing artefact of a volatility claim entering the
> family, predicted in writing before it occurred, and it carries no information about
> direction whatever.
>
> It is also **block-sensitive** and must not be quoted without that: H-009's `p` is
> `0.0008` at block 1, `0.0150` at the registered block 10, and `0.0252` at block 25 — the
> last of which misses `0.025` and would leave the family rejecting nothing at all. A §9
> clearance that turns on the fourth decimal place of a nuisance parameter is not a settled
> clearance.

> **Third note, 2026-07-28 — registering H-011 takes it away again, before H-011 runs.**
> `N_claims` moves 4 → 5, so the BH critical values become `0.01, 0.02, 0.03, 0.04, 0.05`.
> The family's available `p` are `0.0150` (H-009), `0.0204` (H-003) and `0.5041` (H-007):
> rank 1 needs `≤ 0.01`, rank 2 needs `≤ 0.02`, rank 3 needs `≤ 0.03`, and **none holds.**
> The `k = 2` rejection recorded above is removed at the moment of registration — H-003 and
> H-009 both stop clearing §9 until H-011 returns `p ≤ 0.03`.
>
> **The cost is accepted and is nominal.** H-009 was rejected on its own primary threshold,
> not on §9; H-003's directional reading was withdrawn on H-007's substantive grounds.
> Neither result depends on the clearance. What is not nominal is the pattern: this is the
> third time registering a question has visibly weakened an existing result before any data
> was touched, and the third time it was written down first. See H-011 §9.

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

**2026-07-29 — the cost treatment is wrong, and "its arithmetic is unchanged" was too strong**

> Appended, not edited. No re-run, no `N_claims` draw.
>
> The withdrawal above says "the run happened as recorded and its arithmetic is
> unchanged." That is true of the arithmetic *as executed* and it has been read as more
> than it says. **The inputs to that arithmetic are now known to be wrong**: see H-005,
> 2026-07-29. Financing on this broker's gold is price-dependent rather than a fixed
> points rate, and the short side is credited where the model charged it.
>
> **Direction of the correction, which is determinable.** This entry's own cost table
> reports realised swap of **0.000738 R** per decision for the signal arm and
> **0.000672 R** for the random-entry control. The signal arm was **56.2% long**; a random
> arm is 50% long by construction. Correcting to 67.9 charged long and 27.0 credited short:
>
> | arm | registered blended rate | corrected rate | factor | swap, corrected |
> |---|---|---|---|---|
> | signal (56.2% long) | 14.744 | 26.334 | **1.786x** | 0.000738 → 0.001318 R |
> | random (50% long) | 14.000 | 20.450 | **1.461x** | 0.000672 → 0.000982 R |
>
> The signal arm is penalised **0.000271 R more** than the control, because it is more long
> and the long side is where the model understated. **The `+0.060398 R` difference becomes
> `≈ +0.060127 R`** — a change of **0.45%** of the effect.
>
> **What this changes: nothing that matters.** The correction is four orders of magnitude
> smaller than the effect and cannot move `p = 0.0204`. **The directional reading stays
> withdrawn on H-007's grounds**, which are substantive and untouched by any cost figure.
>
> **Stated assumptions**, because the numbers above are arithmetic and not a re-run: the
> mode-2 reading in H-005 finding 3; equal nights-held per decision across directions
> within an arm; a 50/50 direction split in the random control. **No p-value is
> recomputed** — that needs the per-block data and a run, and no run is being made.

**2026-08-01 — the long leg of that correction is now measured; the short leg is not**

> Appended, not edited. No re-run, no `N_claims` draw. **Nothing in the block above changes.**
>
> The 2026-07-29 correction was arithmetic under a stated reading of the published fields.
> `[MEASURED]` H-005, 2026-08-01: the long rate of **67.9 points per lot per night is now a
> measurement** — a live 0.10-lot long was charged 13.58 across two charging events. The
> **27.0 credit on the short side is still only a published field**, and every blended rate
> in the table above depends on it.
>
> **The correction is bounded across both readings of the unmeasured leg**, so the
> conclusion does not wait on measuring it:
>
> | short leg | signal factor | random factor | signal penalised more by | effect becomes |
> |---|---|---|---|---|
> | credited 27.0 (published) | 1.786x | 1.461x | 0.000271 R | +0.060127 R (0.45%) |
> | charged 27.0 (adverse) | 3.390x | 3.389x | 0.000158 R | +0.060240 R (0.26%) |
>
> Either way the correction is under half a percent of the effect and cannot touch
> `p = 0.0204`. **The directional reading stays withdrawn on H-007's grounds**, which are
> substantive and independent of any cost figure. The reading of this entry is unchanged in
> every respect; what changed is that half of the correction's input is now measured rather
> than read off a field.

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

**2026-07-29 — the substitute is measured, and its pessimism assumption is false**

> Appended, not edited. This gate's conditions (i)–(iii) are unchanged and no run is
> re-run. **This is a broker measurement, not an evaluation run: no `hypothesis_id`, no
> `N_claims` draw, `N_claims` stays at 6.** It is recorded here because H-005 is the
> entry that carries the substitute, and the substitute has now been read against a live
> terminal for the first time.
>
> `[MEASURED]` `scripts/risk_monitor.py --probe`, FxPro demo, symbol `GOLD`:
>
> | field | value |
> |---|---|
> | `swap_mode` | **2 — `SYMBOL_SWAP_MODE_CURRENCY_SYMBOL`** |
> | `swap_long` | **−67.9** |
> | `swap_short` | **+27.0** |
>
> **Three findings, and they are different in kind from one another.**
>
> **1. The structure is wrong, not just the magnitude — and this is the substantive one.**
> In `CURRENCY_SYMBOL` the rate is denominated in the symbol's **base** currency, which
> for gold is ounces. The account-currency charge is therefore **proportional to the gold
> price at the moment of charging**: a long held through a rising market pays a rising
> dollar carry. `backtest.costs` charges a **fixed points rate**. No value of that
> constant would have been correct, because the registered model has no term that varies
> with price. This is a difference in kind and it cannot be absorbed by re-tuning
> anything.
>
> The layer's refusal to convert is what surfaced it. `risk.swap.declared_swap` returns a
> `Refusal` rather than picking a price to convert at, and the refusal names the
> structure. Had it defaulted, the structure would have been buried inside a plausible
> number.
>
> **2. The sign is asymmetric. Long pays; short is credited.** `backtest.costs.swap_points`
> charges **both** directions, and says so in its own docstring, on the stated ground that
> a credit is an optimistic assumption about a rate this project had never observed. It
> has now been observed and it is a credit. Charging the short side is a structural error
> in the cost model, independent of magnitude and independent of finding 1.
>
> **3. The magnitude is roughly 3.4x on the long side, under a stated reading.** The
> mode-2 figure cannot be converted from the field alone — 67.9 ounces a night per lot is
> not a possible charge, so the number is not literally base-currency units at face value.
> Read as an effective charge in the deposit currency per lot per night, which the
> magnitude supports and the field cannot confirm:
>
> | side | registered | FxPro `GOLD` | annualised on a 100 oz lot near 2,400 |
> |---|---|---|---|
> | long | 20.0 charged | **67.9 charged** | **3.0% → 10.3%** |
> | short | 8.0 charged | **27.0 credited** | **1.2% → −4.1%** |
>
> Both measured figures are plausible financing rates for a retail gold CFD. **The
> registered one is not**: 3.0% a year on a gold long is below every dollar funding rate
> in the H-006 window. That asymmetry of plausibility is evidence for the reading, and
> **evidence is not a measurement.** One week of a real position settles it, and until it
> does the declared route stays refused.
>
> **A correction to a claim made when this layer was built.** The `src/risk` scope note
> and its swap module asserted that `backtest.costs.rollovers_crossed` "counts five
> rollovers a week and has no triple-swap concept", so that the registered model
> understated a week's carry by two sevenths *on top of* any magnitude error. **That was
> wrong**, asserted from the function's name without reading its body. `[MEASURED]`
> `rollovers_crossed` counts **every** calendar day's 17:00 New York boundary, weekends
> included: **7 over a Monday-to-Monday span, 14 over two weeks.** The registered night
> **count** per calendar week is right. What differs is *when* the nights land — nothing
> is charged at the weekend, three nights are charged on one weekday — and the two miss in
> opposite directions and cancel over whole weeks. `tests/risk/test_clock.py` now measures
> the count against the real function so the premise is pinned rather than believed.
>
> **What this does not do.** It does not re-open this gate's conditions, it does not change
> `SPREAD_FLOOR_POINTS`, and **it triggers no re-run.** The two cost-dependent results
> carry their own dated notes: see H-003 and H-007. Nothing here is a claim about markets.

**2026-08-01 — the magnitude is measured on the long side, and the structure is not**

> Appended, not edited. Conditions (i)–(iii) unchanged, no run is re-run, **no `hypothesis_id`
> and no `N_claims` draw — `N_claims` stays at 6.** A broker measurement, not an evaluation.
>
> `[MEASURED]` a live long of **0.10 lots** on FxPro `GOLD` was charged **13.58 USD across
> two charging events** — 6.79 a night, which on this contract is **67.9 points per lot per
> night**, equal to the published `swap_long` to the last digit.
>
> **Finding 3 is now a measurement, on the long side only.** The 2026-07-29 block read the
> mode-2 figure as an effective deposit-currency charge and said plainly that this was
> "evidence, and evidence is not a measurement." It is now measured. The **short side is
> not**: the position was long, and the +27.0 credit remains a reading of a published field
> that nothing has been charged against. Measuring it needs a short held across a rollover.
>
> **Finding 1 is narrowed, and the narrowing is against the finding.** The *literal*
> base-currency reading is dead: 67.9 ounces a night per lot would be about **277,000 USD**
> at the price it was measured at, four orders of magnitude from 6.79. The field is being
> applied **at face value in the deposit currency, exactly as `SwapMode.POINTS` would apply
> it**, whatever `swap_mode = 2` declares. So the declared mode does not describe the
> charging rule on this symbol.
>
> That does **not** restore the registered model, and it does not settle the structure
> either. A rate proportional to price, with a coefficient calibrated at the price on the
> night it was read, produces exactly the same number. **One price cannot separate a
> constant from a proportionality through that point.** `risk.carry_log` returns
> `UNDETERMINED` on this window and names the two conditions that failed — two charging
> events against a required five, and a monotone price path against a required two
> reversals. The condition that **passed** is the resolution one, and that distinction
> matters: the window failed on *shape*, not on the price being too flat.
>
> **The corrected divergence, on the basis that matches the registry's own unit.**
>
> | basis | broker | registered | ratio |
> |---|---|---|---|
> | per night, long | **67.9** points/lot | 20.0 points/lot | **3.395x** |
> | per calendar week, long | **475.3** points/lot | 140.0 points/lot | **3.395x** |
> | annualised at gold 4,042 | **6.13%** of notional | 1.81% of notional | 3.395x |
>
> **`3.395x` is the figure. Two other numbers are in circulation and both are wrong to
> quote.** `3.64x` is the same measurement on a **per-calendar-day** denominator — 13.58
> over 1.87 elapsed days rather than over 2 nights — and is correct arithmetic on a
> denominator that is not the registry's. `2.60x` was reconstructed on the belief that the
> tool had divided by a five-night registered week; it had not, and the reconstruction is
> internally inconsistent, implying a nightly charge of 52.0 points against the 67.9 that
> was measured. Under a five-night denominator the tool would have printed **5.10x**, so the
> displayed figure is itself evidence that the 2026-07-29 rollover correction reached the
> arithmetic. `tests/risk/test_swap.py` and `tests/risk/test_report.py` reconstruct all
> three numbers so that this paragraph is a test rather than a claim.
>
> **What is still out of reach, restated because it is the most over-readable part.** A 2026
> measurement is 2026 funding. The H-006 window opens in 2015 at near-zero dollar rates.
> **Nothing here licenses a retro-fit of the registry's cost model**, and no one may use
> 67.9 to compute what H-003 or H-007 "should have" charged over 2015–2026.
>
**A fourth objection to the registered structure, which needs no broker reading at all**

> Findings 1–3 above rest on readings of one account. This one is a property of the
> registered model's own **functional form** and would hold if no terminal had ever been
> opened. It is **reasoning, not a result**, and it is recorded at the constants' own site in
> `backtest/costs.py` as well as here.
>
> A charge fixed in **points per lot per night** implies an annualised financing rate, as a
> percentage of notional, of `points × point value × 365 / (contract size × P)` — **inversely
> proportional to price.** `[MEASURED]` against this project's own snapshot over the H-006
> window, at 20 points, 1.00 a point and 100 ounces a lot:
>
> | point in the window | gold | implied rate |
> |---|---|---|
> | opens, 2015-09-11 | 1,111.72 | **6.57% a year** |
> | window low | 1,050.02 | **6.95% a year** |
> | window high | 5,562.51 | **1.31% a year** |
> | closes, 2026-07-24 | 4,052.85 | **1.80% a year** |
>
> So `SWAP_LONG_POINTS_PER_LOT_PER_NIGHT` does not represent *a* financing rate over the
> window. It represents a rate that **falls by a factor of 5.30 as the price rises**,
> monotonically, with no reference to any interest rate — and the span is *exactly* the
> price ratio inverted, which is the argument: the variation is the price path and nothing
> else. Over the same span the dollar policy rate went from near zero to several percent,
> the **opposite** direction.
>
> **The objection is symmetric, and that is what makes it decisive rather than awkward. No
> single points constant can be right at both ends.** Calibrate to 2015 and it is 5.3x too
> small by 2026; calibrate to 2026 — the 67.9 just measured — and it implies **22.29% a
> year** at the window's opening price.
>
> **What this does and does not license.** It bears on the **whole 2015–2026 window** rather
> than on one week, and it says the registered *structure* cannot be right. It does **not**
> say what the right structure is, and it does not license computing what any run "should
> have" charged — a constant that is wrong everywhere is not evidence for any particular
> replacement. `RESEARCH.md` §5.2 is untouched: the constants stay as they are, and this is
> a note beside them. The arithmetic is pinned in `tests/backtest/test_costs.py` so that it
> is a test rather than a paragraph.

**2026-08-06 — seven nights, and what an aggregate can and cannot do**

> Appended, not edited. No re-run, **no `hypothesis_id`, no `N_claims` draw — `N_claims` stays
> at 6.** Taken after the clock defect of 2026-08-02 was fixed: offset `+3.0` measured from a
> live tick, `opened_at` correct, both guards silent.
>
> `[MEASURED]` a live long of **0.10 lots**, held **171.6 hours across 7 nights**, was charged
> **47.53** in the deposit currency while gold moved **4,090.38 → 4,261.46 (+4.18%)**. That is
> **6.79 a night**, **67.900 points per lot per night**, equal to the published `swap_long` to
> three decimals.
>
> **The aggregate cannot bear on price-dependence. Not weakly — exactly not at all.**
>
> Under `PRICE_DEPENDENT` the charge on night `n` is `k·P_n`, so the total is `k·Σ P_n =
> k·N·P̄`. Under `FIXED_RATE` it is `c·N`. Each model has **one free parameter** and the total
> is **one number**: exactly identified, zero degrees of freedom left for a test. The reason is
> that `P ↦ k·P` is **linear**, so `E[k·P] = k·E[P]` — the mean charge *is* the charge at the
> mean price, and the aggregate is invariant to everything the shape test exists to see. A
> monotone path, a V, and a path oscillating over a 24% range with the same mean all produce
> **the identical total**. Pinned in `tests/risk/test_carry_log.py`.
>
> **So the seven-night total settles the magnitude and nothing about the structure**, exactly
> as the 2026-08-01 two-night total did. More nights do not help. This is a property of the
> statistic, not of the sample size.
>
> **The total compared against the published field is a different comparison, and it is
> evidence.**
>
> This is the part that must not be left ambiguous. The observation is not "the total was
> 47.53". It is "the total was 47.53 **and the broker independently publishes 67.9**". Under
> `PRICE_DEPENDENT` with a static calibration price `P_ref`, the mean charge is
> `67.9 · P̄/P_ref`, so observing exactly 67.9 **pins `P_ref = P̄`**. The posting resolution is
> one cent on the total, which over seven nights is **±0.0105%** on the rate — so `P_ref` is
> pinned to this week's mean price within about ±0.44 dollars.
>
> | if the field were a coefficient calibrated at… | expected total | observed | gap |
> |---|---|---|---|
> | the week's opening price, 4,090.38 | **48.52** | 47.53 | **99x** the posting resolution |
> | the week's closing price, 4,261.46 | **46.58** | 47.53 | **95x** the posting resolution |
> | this week's mean, 4,175.92 | 47.53 | 47.53 | — |
>
> `[MEASURED]` against this project's own snapshot, the odds of a fixed calibration price
> landing in that window by chance, under a uniform prior over gold's recent range:
>
> | prior over when the broker last calibrated | gold's range | odds against |
> |---|---|---|
> | trailing 1 month | 3,963–4,188 | **1 in 257** |
> | trailing 3 months | 3,963–4,767 | **1 in 917** |
> | trailing 1 year | 3,269–5,563 | **1 in 2,615** |
>
> A uniform prior is *generous* to price-dependence: it assumes the broker is as likely to have
> calibrated at this particular week's mean as anywhere else, and nothing makes that true.
>
> **The verdict: evidence, not coincidence — and it is evidence for the reading, not the
> structural test's answer.** Two things follow and they must not be run together.
>
> 1. Against a **static** price-dependent calibration, the match is a two-to-three-order-of-
>    magnitude likelihood ratio in favour of the field being applied at face value. That is
>    strong, it is Bayesian reasoning with a stated prior, and it is **not a measurement.**
> 2. Against a **re-quoted** price-dependent rate — the broker resetting `swap_long` as gold
>    moves — the match is worth **nothing**, because under that hypothesis the charge tracks
>    the field by construction. The discriminator is whether the *field itself* moved, which
>    the log has recorded on every reading since 2026-08-01 and which
>    `risk.carry_log.FieldStability` reports.
>
> **The pre-committed instrument is unchanged and still governs.** `MIN_RESOLVED_NIGHTS = 5`,
> `MIN_REVERSALS = 2`, `SEPARATION_FACTOR = 3` are as fixed in 2026-07-30 as they were then.
> Nothing above is permitted to substitute for them, and **no threshold was moved in the light
> of this reading.** The reasoning is recorded because burying it would be choosing which
> arguments to publish; the verdict still comes from the log.

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

**2026-07-29 — the cost treatment is wrong, and the correction moves toward the signal**

> Appended, not edited. No re-run, no `N_claims` draw. **The verdict above is unchanged.**
>
> This is recorded prominently because it is **the only correction this project has found
> that moves a number in the signal's favour**, and a record that buried it would be
> selecting which corrections to publish.
>
> Financing on this broker's gold is price-dependent and credits the short side: H-005,
> 2026-07-29. This entry's cost table reports realised swap of **0.000738 R** for the
> signal and **0.000959 R** for always-long. Always-long is **100% long**; the signal is
> **56.2% long**. The long side is exactly where the registered model understated, so
> always-long is penalised far harder:
>
> | arm | registered rate | corrected rate | factor | swap, corrected |
> |---|---|---|---|---|
> | signal (56.2% long) | 14.744 | 26.334 | **1.786x** | 0.000738 → 0.001318 R |
> | always-long (100% long) | 20.000 | 67.900 | **3.395x** | 0.000959 → 0.003256 R |
>
> Always-long worsens by **0.001737 R more** than the signal. The measured difference was
> the signal **behind by 0.000141 R**; corrected it is the signal **ahead by
> ≈ 0.001596 R**. **The sign of the point estimate flips.**
>
> **The verdict does not, and the reason is in the numbers already recorded here.** The
> registered block-10 bootstrap gave a 95% CI of **[−0.074192, +0.072810]**, a half-width
> of about **0.0735 R**. The correction is **0.001737 R — 2.4% of that half-width.** It
> moves a point estimate that was never distinguishable from zero to a different point
> estimate that is still not distinguishable from zero. `p = 0.5041` before; there is no
> basis on which 2.4% of a confidence interval turns a coin flip into a result.
>
> **This must not be read as reviving the signal, for three independent reasons.**
>
> 1. The corrected difference is **2.4% of its own confidence interval**. It is noise.
> 2. It is **2.6%** of H-003's `+0.060398 R`, the effect H-007 attributed to long bias.
>    Attributing 2.6% of it to a cost artefact leaves the attribution intact.
> 3. **H-012 looked for directional information directly** — ten features, three horizons,
>    four pre-registered criteria — and did not find it. A financing correction cannot
>    manufacture direction that a direct test looked for and failed to see.
>
> **Stated assumptions**: the mode-2 reading in H-005 finding 3; equal nights-held per
> decision across directions within the signal arm. **No p-value is recomputed**; that
> needs a run, and none is being made. **`REJECTED` stands. H-008 stays unrun.**

**2026-08-01 — the factor that carries this correction is now measured, and a slip in it is corrected**

> Appended, not edited. No re-run, no `N_claims` draw. **`REJECTED` stands. H-008 stays unrun.**
>
> **The measured input.** `[MEASURED]` H-005, 2026-08-01: a live 0.10-lot long was charged
> 13.58 across two charging events — **67.9 points per lot per night**. Always-long is 100%
> long, so the **3.395x** factor that does all the work in the table above is now a
> measurement rather than a reading of a published field. The signal arm's blended 26.334
> still depends on the **unmeasured** 27.0 short credit.
>
> **An arithmetic slip in the block above, corrected here rather than edited there.** That
> block states the gap as `0.001737 R` and the corrected difference as `≈ +0.001596 R`. Its
> own table gives `0.003256 − 0.000959 = 0.002297` against `0.001318 − 0.000738 = 0.000580`,
> and **`0.002297 − 0.000580 = 0.001717`**, not `0.001737`. The corrected point estimate is
> therefore **`≈ +0.001576 R`** and the correction is **2.34%** of the CI half-width rather
> than 2.4%. The error is 1.2% of a quantity that was already 2.4% of a confidence interval;
> it changes nothing and is recorded because an uncorrected number in a registry is a number
> someone will quote.
>
> **The sign flip survives the unmeasured leg.** The short credit is the one input still
> unmeasured, and the conclusion does not depend on it:
>
> | short leg | always-long penalised more by | corrected difference | share of CI half-width |
> |---|---|---|---|
> | credited 27.0 (published) | 0.001717 R | **+0.001576 R** | 2.34% |
> | charged 27.0 (adverse) | 0.000533 R | **+0.000392 R** | 0.72% |
>
> **The point estimate flips sign under both**, and under both it remains a fraction of a
> confidence interval that contains zero comfortably. The three reasons in the block above
> are untouched: it is noise against its own interval, it is a few percent of the effect
> H-007 attributed to long bias, and **H-012 tested for direction directly and found none.**

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

### H-009 — Does the feature layer forecast *volatility* at H = 24?

- **Registered:** 2026-07-28 13:02 UTC
- **Class:** claim — counts toward `N_claims`, taking it **3 → 4**
- **Status:** **REJECTED** — `BSS +0.024157 < 0.05`. The mechanism is confirmed and the
  magnitude is not. (Corrected 2026-07-28 at close-out: this line still read `REGISTERED`
  after the run. The verdict was always in the run block and in §0's counters; the header
  disagreed with both, which is exactly what a reader skimming for status would have been
  misled by.)

**Why this exists, stated first because it determines how a failure is read**

> H-003 and H-007 established that these three features carry no *directional* information
> at `H = 24`. That leaves two explanations that no directional experiment can separate:
> the instrument carries no extractable directional signal, or **the feature layer is not
> measuring anything at all** — a wiring defect in feature computation, alignment, the
> fold geometry, the eligibility mask, or the label path.
>
> Volatility separates them, because volatility is the one quantity on this instrument
> where the prior is strong enough that a null result is not attributable to the market.
> Gold volatility clusters; `realized_vol_24` is a direct measurement of that clustering;
> and forecasting whether volatility will be above its own recent level one window ahead is
> close to the easiest honest forecasting problem this data supports.
>
> This is therefore a **diagnostic with a strong prior**. Its value is asymmetric and that
> is deliberate: a PASS says little that is new, a FAIL says something large.

**Claim**

> A logistic combination of `log_return_24`, `realized_vol_24` and `range_position_48`,
> fitted on the H-001 walk-forward geometry, will achieve **BSS ≥ 0.05** out of sample on
> the volatility label defined in §B, at a one-sided bootstrap `p` clearing the
> Benjamini–Hochberg threshold computed in §D.

---

#### §A. Change under test

> Exactly one thing changes from H-001's unshuffled control: **the label**. Same three
> features, same combiner, same folds, same purge and embargo, same snapshot, same window,
> same standardiser, same eligibility construction.
>
> Files added: `src/labels/volatility.py`, `tests/labels/test_volatility.py`,
> `scripts/run_h009.py`. **Nothing under `src/` is modified.**
>
> **No feature is added, changed, or removed.** This is what makes the run cheap: no new
> causal-test burden under `CLAUDE.md` Hard Rule 1, because no new feature exists.

> **Amendment, 2026-07-28 13:41 UTC — before the run, and made because a guard fired.**
>
> This section first read "one accessor added to `src/models/logistic.py`
> (`coefficients`, read-only, no arithmetic change) so §G can be reported." That accessor
> was written, and `tests/evaluation/test_sensitivity.py` failed:
> `combiner_fingerprint()` moved from `9b09e248…` to `666d3ff7…`.
>
> The guard is correct and its firing is not a false positive to be waved through. K-1's
> sensitivity baseline — which leak modes trip at four parameters — is a property of the
> combiner, and `REPRODUCIBILITY.md` §6 makes any combiner change without a recorded
> re-measurement invalidate every subsequent K-1 pass. The fingerprint is an AST hash
> precisely so it cannot be argued down as "only a comment".
>
> There were three available responses and only one of them is honest:
>
> | response | verdict |
> |---|---|
> | bump `RECORDED_COMBINER_FINGERPRINT` | **no.** `sensitivity.py` names this as "the exact defect §6 prohibits" |
> | re-run the harness-validation sweep and re-record | legitimate, but it spends a run to enable a diagnostic readout |
> | **do not change the combiner** | **taken** |
>
> §G's prediction is unchanged in substance. What changed is how it is read: instead of
> the raw weight, the run probes the *fitted model's response* — the change in predicted
> probability from a one-SD step in `realized_vol_24` with the other standardised features
> held at zero. The sigmoid is monotone in the linear predictor, so the sign of that
> response is the sign of the coefficient, and the magnitude is in probability units rather
> than in units of a standardised weight.
>
> The behavioural probe is the better instrument on its own merits under `EVALUATION.md`
> §14: it interrogates the fitted model from outside rather than reading its internals.
> That it is also the reading that leaves the guard intact is the point being recorded —
> **the guard changed the design rather than being adjusted to permit it.**

#### §B. The label — `vol_above_median_24`

> Let `rv = RealizedVol(24)` — the shipped feature, unchanged, causally tested under H-002.
>
> ```
> threshold[T] = median( rv[T-999], ..., rv[T] )          # 1000 values, all <= T
> label[T]     = 1.0  if  rv[T + 24] > threshold[T]  else  0.0
> ```
>
> **Why `rv[T + 24]` is the forward realised volatility, exactly.** `rv[k]` is the
> population SD of the one-bar log returns computed from closes `k-24 .. k`. So `rv[T+24]`
> is the SD of returns from closes `T .. T+24` — the window *after* `T`. The forward
> quantity is the trailing feature read 24 bars later, so the estimator is identical to the
> one in the feature column by construction rather than by a second implementation that
> could drift from it.
>
> **The two windows share no returns.** Trailing uses returns indexed `T-23 .. T`; forward
> uses `T+1 .. T+24`. Disjoint. There is no mechanical correlation from an overlapping bar.
>
> **The label looks forward and that is correct** (`src/labels/direction.py` states the same
> rule). What must *not* look forward is `threshold[T]`, which is a trailing statistic and
> is held to `DATA_CONTRACT.md` §1 by a truncation test — see §F.
>
> **Tie rule:** strict `>`. An exact tie resolves to `0`, matching the direction label's
> convention. Reported as a tie rate, not left implicit.
>
> **Validity.** A label is undefined where the forward window `[T, T+24]` touches an invalid
> bar (`label_validity`), and where the backward span `[T-1023, T]` does
> (`feature_validity` at `L = threshold_window + vol_window = 1024`). Never imputed
> (`DATA_CONTRACT.md` §6).

#### §C. What is reused unchanged, and why that is the point

> | component | reused | note |
> |---|---|---|
> | features | `LogReturn(24)`, `RealizedVol(24)`, `RangePosition(48)` | byte-identical to H-001 |
> | folds | `walk_forward_folds`, 5 folds, `FIRST_TEST_FRACTION = 0.50`, spacing 24 | H-001 |
> | combiner | `LogisticRegression` + `Standardizer`, 4 parameters | H-001 |
> | scorer | `brier_skill_score` against in-window climatology | `EVALUATION.md` §3.2 |
> | K-1 harness | `run_shuffled_label_study`, 30 seeds | `EVALUATION.md` §5.1 |
> | bootstrap | `backtest.metrics.bootstrap_mean`, stationary, Politis–Romano | H-003 §F |
>
> A different label on identical machinery is the only configuration in which a null
> directional result and a positive volatility result can be attributed to the label rather
> than to anything else.

#### §D. Primary metric, threshold, and the multiple-testing consequence — stated before the run

> **Primary metric:** pooled out-of-sample Brier Skill Score across the five folds.
> **Threshold:** `BSS >= 0.05` **and** the §E `p`-value clears Benjamini–Hochberg.
>
> `0.05` is not chosen here. It is K-3's materiality floor, which `EVALUATION.md` §5.1
> already describes as the level "below which 'edge' is not a coherent claim". Using the
> project's existing floor rather than a fresh one removes a degree of freedom.
>
> **A BSS of 0.03 is a FAIL under this registration.** Recording that now so it cannot be
> reread afterwards as a partial success.
>
> **The BH arithmetic, computed in advance.** Registering this claim moves `N_claims` from
> 3 to 4. At `m = 4, α = 0.05` the step-up critical values are `0.0125, 0.025, 0.0375,
> 0.05`. The family's observed `p`-values are H-003 `0.0204`, H-007 `0.5041`, H-004 unrun
> (counts in `m`, can never be rejected), and H-009 `p`.
>
> Working the step-up through:
>
> | condition | requires |
> |---|---|
> | `k = 1` rejects | `min(p, 0.0204) <= 0.0125` → `p <= 0.0125` |
> | `k = 2` rejects | `max(p, 0.0204) <= 0.025` → `p <= 0.025` |
> | `k = 3` rejects | `0.5041 <= 0.0375` → impossible |
>
> **So H-009's registered BH threshold is `p <= 0.025`.**
>
> **And a consequence that must be stated before the run, not discovered after it.** BH is
> step-up: whenever H-009 clears at `p <= 0.025`, `k = 2` holds and the procedure rejects
> the two smallest `p`-values — which includes **H-003 at 0.0204**. A volatility result
> would drag a directional claim across §9's line.
>
> > **This does not restore H-003's directional reading, and nothing may later present it as
> > having done so.** H-003's reading was withdrawn on H-007's substantive grounds —
> > always-long matched the signal — not on §9's. Clearing a multiple-testing correction is
> > not evidence about direction. The coupling is a mechanical artefact of putting a
> > volatility claim and a directional claim in one BH family, which `EVALUATION.md` §9's
> > "across all hypotheses" wording requires and which is not being reinterpreted here.
>
> That artefact is registered as an observation, and the family construction is left alone.

#### §E. The `p`-value, and why it is not the shuffled-labels null

> **Construction.** Per decision `i`, let `d_i = (base_rate − y_i)² − (p_i − y_i)²`, the
> improvement in squared error over the climatological forecast. `mean(d) > 0` if and only
> if `BSS > 0`. The `p`-value is one-sided, `H0: mean(d) = 0` against `H1: mean(d) > 0`,
> from the stationary bootstrap already registered under H-003 §F:
>
> | constant | value |
> |---|---|
> | expected block | **10**, sensitivity reported at **1** and **25** |
> | resamples | 10,000 |
> | seed | 1337 |
>
> Identical to H-003 and H-007, so the three are comparable without a caveat.
>
> **Why not a permutation `p` from the 30 shuffled seeds.** Its floor is `1/31 = 0.032`,
> above this hypothesis's own BH threshold of `0.025`. A test whose smallest attainable
> `p` cannot clear its own threshold cannot pass, and choosing more seeds *after* noticing
> that would be selecting the instrument to fit the bar. The shuffled-labels study still
> runs, as K-1, for what it is for.

#### §F. Gates that must clear before the primary metric may be read

> | gate | condition | status if it fails |
> |---|---|---|
> | K-1 | shuffled-labels study on **this label**, 30 seeds, all three §5.1 conditions | **halt** — the result is void, not negative |
> | K-1 fixtures | `label_in_features` and `target_encoding_on_all` must trip | **void** — the gate cannot fire, so its silence means nothing |
> | K-6 | `>= 150` decisions on the grid | **no result**, not a negative one |
> | threshold causality | `threshold[T]` bit-identical when recomputed on `df.iloc[:T+1]` | **halt** — K-2 in substance |
>
> **K-1 is re-run rather than inherited.** H-001 cleared K-1 for the *direction* label. The
> label is the one thing changing here, and the label path is exactly where a new leak could
> enter, so inheriting the clearance would be inheriting it across the change it is meant to
> cover.
>
> **The threshold-causality check ships with an adversarial fixture** — a deliberately
> centred (non-trailing) threshold that the same check must reject — per `EVALUATION.md`
> §14. A truncation check that has never failed is indistinguishable from one that cannot.

#### §G. Registered predictions — reported, and explicitly not pass conditions

> Two predictions are recorded now so that agreement is evidence rather than hindsight. Per
> the H-008 precedent, neither is a pass condition: making a surprising-but-legitimate
> mechanism a failure builds a gate that fires on correctness.
>
> **(i) The fitted model's response to `realized_vol_24` will be positive**, in every fold.
> Volatility persists, so high current volatility should raise the predicted probability
> that forward volatility exceeds the six-week median. Measured as the change in predicted
> probability from a one-SD step in `realized_vol_24` with the other standardised features
> held at zero — a route that shares nothing with the BSS computation, which is a deliberate
> application of §14, since a self-check that shares the assumption is what let three of
> five prior defects through. (See §A's amendment for why this is the probe rather than the
> raw coefficient.)
>
> > A high BSS with a **negative** response is a flag: it means the model is winning for a
> > reason opposite to the registered mechanism, and the PASS must not be acted on until
> > that is explained. Flag, not verdict.
>
> **(ii) `realized_vol_24` alone will account for most of the skill.** A single-feature
> variant is reported as an attribution diagnostic.
>
> > It is **not a competing configuration and cannot become the primary**, whatever it
> > scores. The primary is the three-feature model, fixed here. Reporting two and keeping
> > the better one is metric shopping under `RESEARCH.md` §5.3.

#### §H. A known confound of this diagnostic, and its pre-committed non-rescue

> The threshold adapts to the local volatility level; the feature does not. `Standardizer`
> is fitted per fold on training rows, so a test era whose volatility level has shifted away
> from its training prefix will degrade the mapping for reasons that are about
> non-stationarity rather than about whether the feature layer works.
>
> This is real and is not being designed away — designing it away would need a new feature,
> which would need a causal test, which is the burden this hypothesis exists to avoid.
> Instead: **per-fold BSS is reported alongside the pooled figure**, so a level-shift
> signature (strongly positive in some folds, strongly negative in others) is visible rather
> than confounded into one number.
>
> > **Pre-committed:** fold-dependence is *reported* and does **not** rescue a pooled
> > failure. A feature layer that forecasts volatility in two folds out of five is not a
> > feature layer the next slice can be built on. If the pooled BSS misses 0.05, the verdict
> > is FAIL whatever the per-fold pattern looks like.

#### §I. Constants introduced by this hypothesis

> | constant | value | class | note |
> |---|---|---|---|
> | horizon `H` | 24 bars | **forced** | matches H-001's registered horizon so the comparison to H-003/H-007 is apples-to-apples |
> | vol window | 24 bars | **forced** | must equal `H` for `rv[T+H]` to be the forward realised vol |
> | threshold window | **1000 bars** | **judgement** | ~6 weeks of H1 bars: long relative to volatility's persistence half-life, so the label is a question about level rather than about change; short enough not to be a whole-sample constant, which would import the global distribution into the label |
> | BSS threshold | 0.05 | **forced** | K-3's existing materiality floor, not a new number |
> | BH threshold | `p <= 0.025` | **derived** | §D, from `m = 4` and the family's existing `p`-values |
> | bootstrap block / resamples / seed | 10 / 10,000 / 1337 | **forced** | H-003 §F |
>
> **One judgement constant, and it is not swept.** A sensitivity sweep over the threshold
> window would not be a sensitivity analysis: it changes the label, therefore the question,
> therefore the hypothesis. Three windows would be three hypotheses under `EVALUATION.md`
> §9 and metric shopping under `RESEARCH.md` §5.3. 1000 is fixed here, before the run, and
> is not revisited on the basis of what this run returns.

#### §J. Pre-committed interpretation

> **PASS — `BSS >= 0.05` and `p <= 0.025`, with §F clear.**
>
> > The feature layer measures something real, and the pipeline can extract it and score it
> > out of sample at `H = 24`. The directional null from H-003/H-007 is then a statement
> > about **direction specifically**, not about the project's wiring. Slice 1 — the
> > capacity-ceiling measurement — becomes a meaningful test, because a null result from it
> > could then be attributed to the absence of directional signal rather than to a broken
> > instrument.
>
> **FAIL — anything else.**
>
> > **The feature layer itself is in question, not the horizon.** This is the reading, and
> > it is registered now precisely because the tempting alternative reading — "H = 24 is the
> > wrong horizon for volatility" — will be available afterwards and is wrong.
> >
> > The argument: volatility persistence is the strongest prior available on this
> > instrument, `realized_vol_24` is a direct measurement of the quantity being forecast,
> > and the forecast window is the same length as the measurement window. If a direct
> > measurement of a persistent quantity cannot forecast that quantity one window ahead,
> > the defect is **upstream** — in feature computation, in bar alignment, in the fold
> > geometry, in the eligibility mask, or in the label path — and not in the choice of
> > horizon and not in the market.
> >
> > **Required action on FAIL: audit the feature layer against external references, and do
> > not run slice 1.** A capacity-ceiling measurement on a broken instrument returns a low
> > ceiling and would be misread as "no signal exists on this instrument" — which is exactly
> > the false conclusion this hypothesis is ordered first to prevent. The audit is the work;
> > "investigate further" is not an action and is not what this says.
>
> **AMBIGUOUS — `BSS >= 0.05` but `p > 0.025`, or the 95% CI straddling 0.05.**
>
> > REJECT, per the template's default. Tie goes to the null.

#### §K. What a PASS licenses, and what it does not

> Licenses: **slice 1 only** — the capacity-ceiling measurement, registered separately
> before it runs.
>
> Does not license: any trading claim, any rung of `EVALUATION.md` §2, any agent. This
> hypothesis has **no cost model, no baseline ladder, and no trade** — volatility
> forecastability as defined here is not a tradeable edge and must never be reported as one.
> The ladder remains halted at rung 2.
>
> Explicitly recorded: if slice 1 is registered after a PASS here, **K-1 must be re-measured
> at the new capacity.** `RETROSPECTIVE.md` §3 measured K-1 blind to `train_test_overlap` at
> four parameters, and detectability is a property of the estimator. A high-capacity model
> inherits nothing from the current clearance.

#### §L. Why this is a claim and not a gate

> It reads like machinery-checking, which is what gates do, and the registry's own
> definition would let it be argued either way. It is registered as a **claim** for two
> reasons:
>
> 1. It asserts skill (`BSS >= 0.05`) on real labels. That is edge-seeking in *form* whatever
>    the intent, and a false positive here is possible in a way it is not for K-1 or K-2.
> 2. A PASS is favourable and licenses further work. Anything that can license work by
>    coming out one way is something there is an incentive to shop for, and the correction
>    exists for exactly that.
>
> Counting it costs `N_claims` and tightens every threshold in the family, including its
> own. That is the conservative direction and it is the right one.

**Sample size expected**

> ~1,300 decisions on the registered grid, against K-6's floor of 150. Slightly below
> H-003's 1,364 because the 1,024-bar backward span invalidates more of the series head than
> the 48-bar feature lookback did. Exact count reported before the verdict; label-free, so
> it is known without seeing a result.

**Dataset & window**

> Snapshot `71f9fcf1…`, window `2015-09-11` → `2026-07-26` (H-006). Walk-forward, five
> folds. **The sealed holdout is not opened and is not involved.**

--- RUN ---

- **Run manifest:** `runs/dc0f40bc-422c-433f-8790-4567a0408843.json`,
  sha256 `0c2ed357abf70ebe9597922968a0cfca1ceba8fdd0ae8fd8aa79248ff9152f89`
- **Executed:** 2026-07-28, commit `ea4dc33`, clean tree
- **Registration commit:** `8e01d7d` — provably before `ea4dc33`, which added the code
- **Verdict:** **REJECTED**

**Setup as executed**

> 65,395 in-window bars, 12 invalid. Label defined on 59,976; eligible 59,976; **1,333
> decisions** on the registered grid, K-6 clear at 8.9x. Base rate `0.489872`, **zero ties**.
>
> Fold 0 carries 242 decisions against the other folds' 273, and reports `purged = 0` where
> H-001 reports 24. Checked rather than assumed: the two unexplained 2021-01-21 gaps sit at
> bars 32404-32405, and the label's 1,024-bar backward span poisons `[32404, 33428]`, which
> straddles fold 0's `test_start` of 32697. All 24 purge candidates were already ineligible,
> so **the purge found nothing left to purge** rather than failing to run. `731 / 24 = 30.5`
> grid points lost, and 31 are missing. The wider backward span makes each invalid bar
> poison 1,024 bars where a 48-bar feature lookback poisoned 48.

**Gates**

> | gate | result |
> |---|---|
> | K-1 on this label, 30 seeds | **PASS** — mean BSS `-0.000834`, CI `[-0.001394, -0.000445]`, median `-0.000435`, max `+0.000479` |
> | `label_in_features` fixture | TRIPPED, `+0.999984` |
> | `target_encoding_on_all` fixture | TRIPPED, `+0.241980` |
> | K-6 | 1,333 vs 150 |
> | threshold causality + adversarial fixture | enforced in CI, 454 tests green |

**Primary metric**

> | | |
> |---|---|
> | **pooled BSS** | **`+0.024157`**, n = 1,333 |
> | registered threshold | `>= 0.05` — **NOT CLEARED** |
> | BS model / climatology | `0.243861` / `0.249897` |
>
> Per fold: `-0.010530` (n=242), `+0.021558`, `+0.010775`, `+0.024594`, `+0.064928`.

**Significance**

> | block | mean d | 95% CI of mean d | one-sided p | BSS CI |
> |---|---|---|---|---|
> | 1 | `+0.006037` | `[+0.002368, +0.009662]` | `0.0008` | `[+0.0095, +0.0387]` |
> | **10 (registered)** | `+0.006037` | `[+0.000972, +0.011532]` | **`0.0150`** | **`[+0.0039, +0.0461]`** |
> | 25 | `+0.006037` | `[+0.000455, +0.012077]` | `0.0252` | `[+0.0018, +0.0483]` |
>
> **The BSS interval excludes 0.05 from below at all three block lengths.** This is not the
> AMBIGUOUS branch and not a knife-edge: the threshold is outside the interval, not inside it.

**The registered predictions, scored**

> | prediction | outcome |
> |---|---|
> | §G (i) response to `realized_vol_24` positive in every fold | **confirmed 5/5** — `+0.0840, +0.0824, +0.0837, +0.0800, +0.0828` |
> | §G (ii) `realized_vol_24` accounts for most of the skill | **confirmed** — alone it scores `+0.023485`, **97.2%** of the three-feature BSS |
> | §E mean(d) > 0 | confirmed, `p = 0.0150` |
> | §D BH coupling to H-003 | fired exactly as written, see below |
>
> The probe reproduced the evaluation path's probabilities bitwise, so the refit is the same
> model rather than a second implementation asserted to be equivalent.

**Verdict: REJECTED, and the reason the FAIL branch's argument does not survive its own run**

> `BSS +0.024157 < 0.05`. The threshold was registered at K-3's existing materiality floor
> before the run and it does not move. **H-009 is rejected.**
>
> **And the §J FAIL branch is wrong on the facts, which is a defect in this registration and
> is recorded as one.** §J justified its action with: "if a direct measurement of a
> persistent quantity cannot forecast that quantity one window ahead, the defect is
> upstream." The run measured that it **can** forecast it — significantly, through the
> predicted mechanism, with the predicted feature carrying 97.2% of the effect and the
> predicted sign in all five folds. Four pre-registered predictions were confirmed. The
> antecedent of §J's argument is false.
>
> **What went wrong in the registration:** it set a binary threshold on a diagnostic whose
> informative content was not binary, and it registered the *sign* and the *attribution* of
> the effect while registering nothing about its *magnitude* — and magnitude is what decided
> the verdict. "Does the feature layer work" and "does it reach BSS 0.05" were bound together
> as one question when they are two, and no prediction was recorded that would let this run
> distinguish "the layer is lossy" from "the label is harder than assumed".
>
> **The action stands anyway. Slice 1 is not run.** §J's required action was registered
> before the result and is not being overridden on the basis of the result, which is the
> whole mechanism this registry exists to enforce. A registration that turns out to have
> been poorly constructed is corrected by a **new hypothesis**, registered before it runs —
> never by rereading the old one in the light of what it returned. `RESEARCH.md` §5.2 does
> not carve out an exception for registrations whose author later disagrees with them.
>
> What the project may now assert, and no more: **the feature layer is connected to the
> label through the registered mechanism, and the effect it carries is below the materiality
> floor the project set for itself.** Whether that magnitude indicts the feature layer, the
> four-parameter combiner, or the difficulty of the label is **unresolved, and this run
> cannot resolve it** because no prediction was registered that would have separated them.

**§9 — the BH consequence, which fired as written**

> `p = 0.0150 <= 0.025`. At `m = 4` the step-up finds `k = 2`: sorted `p` are `0.0150`
> (H-009) and `0.0204` (H-003), and `0.0204 <= 2/4 x 0.05 = 0.025`. **Benjamini-Hochberg
> rejects both nulls.** H-003 clears `EVALUATION.md` §9 for the first time in the project's
> life.
>
> **H-003's directional reading is not restored and nothing may present it as restored.**
> It was withdrawn on H-007's substantive grounds — always-long matched the signal at
> `p = 0.5041` — not on §9's. This consequence was written into §D and into H-003's own
> entry *before* this run for exactly this reason.
>
> **Reported without softening: the coupling is block-sensitive.** At the registered block
> `p = 0.0150` and at block 1 `p = 0.0008`, both clearing. At block 25 `p = 0.0252`, which
> **misses 0.025 by 0.0002** and would leave the family rejecting nothing. A cross-hypothesis
> consequence that turns on the fourth decimal place of a nuisance parameter is not a robust
> consequence, and H-003's §9 clearance should be read as holding at the registered block and
> failing at the stress block rather than as settled.

**Notes**

> - No cost model, no trade, no baseline ladder, no holdout. H-005's deviation does not
>   apply and no `EVALUATION.md` §10 claim is made. The ladder remains halted at rung 2.
> - `src/` was not modified for this run — see §A's amendment. `models/logistic.py` is
>   byte-identical, so K-1's recorded sensitivity baseline still describes this combiner.
> - Any new idea in this block becomes a **new hypothesis**, not an amendment to this one.

---

## 6. Capacity — separating the three explanations H-009 named and could not resolve

H-009's verdict block states the open question in the project's own words:

> "Whether that magnitude indicts the feature layer, the four-parameter combiner, or the
> difficulty of the label is **unresolved, and this run cannot resolve it** because no
> prediction was registered that would have separated them."

| # | explanation | status after H-009 |
|---|---|---|
| A | **the features** are lossy — they carry the mechanism but little of it | untested against the alternatives |
| B | **the combiner** — four parameters — cannot express what is there | untested directly; see the positive control below |
| C | **the label** — 24-bar direction, ε = 0.01 — is harder than assumed | untested |

The proposed slice 1 (≈50 candidate features at higher capacity) changes **feature count
and capacity simultaneously** and would return a number that A, B and C all explain.
H-010 and H-011 exist to remove B from the list first, because B is the cheap axis: the
same features, the same label, the same folds, the same snapshot, a larger combiner.

**H-009 is already a partial positive control for B, and it points against B.** The same
four-parameter combiner, on the same three features, over the same folds and window,
extracted `BSS +0.024157` at `p = 0.0150` on the volatility label — with
`realized_vol_24` alone accounting for 97.2% of it. Four parameters are demonstrably able
to express real structure in these features **when there is structure to express.** That
is a prior, not a result: volatility is more persistent and more autocorrelated than
direction, so a class adequate for one is not thereby adequate for the other. H-011
registers the prediction that follows from it and scores it, rather than assuming it.

**This section corrects a defect H-009 recorded in itself.** H-009 §J "registered the
*sign* and the *attribution* of the effect while registering nothing about its
*magnitude* — and magnitude is what decided the verdict." Two questions were bound to one
threshold. H-011 registers three statements, three metrics, three thresholds.

---

### H-010 — K-1 sensitivity re-measured at every capacity rung

- **Registered:** 2026-07-28 UTC
- **Class:** gate — does not count toward `N_claims`
- **Status:** **REJECTED** — the four pass conditions are "all required", and (iv) cannot
  be satisfied at C-3, C-4 or C-5. Passes at C-0, C-1, C-2. H-011 does not execute.
- **Order:** must PASS before H-011 executes. An H-011 run that predates this gate's
  result is **VOID**, not "pending confirmation".

**What this is**

> `REPRODUCIBILITY.md` §6 already states the rule and already enforces it:
> `src/evaluation/sensitivity.py` holds `RECORDED_COMBINER_FINGERPRINT` alongside the
> recorded baseline, and `tests/evaluation/test_sensitivity.py` fails the build when the
> fingerprint moves without a matching re-measurement.
>
> This is not a new rule. It is the registration of the measurement that rule demands,
> **written before the combiner changes rather than after** — because the guard fails the
> build without saying what the answer must be, and a build failure is repaired by editing
> constants. `EVALUATION.md` §14: three of five instrument defects had a self-check that
> agreed with them, because the self-check shared the assumption. A re-measurement whose
> pass condition is written after seeing its own output is that shape exactly.

**A gap in the existing guard, found while registering this and fixed by it**

> The fingerprint is taken over `src/models/logistic.py`. H-011 raises capacity by
> **expanding the design matrix**, not by editing the estimator — so `logistic.py` stays
> byte-identical and **the guard as built would not fire.** `RECORDED_N_FEATURES = 3` and
> `RECORDED_PARAMETER_COUNT = 4` would silently continue to describe a 20-parameter fit.
>
> H-009's Notes relied on exactly this property in the safe direction ("`models/logistic.py`
> is byte-identical, so K-1's recorded sensitivity baseline still describes this combiner"),
> which was true there and is *not* true here. The guard must key on the **effective
> parameter count of the fitted design matrix**, not on the estimator module's AST alone.
> Extending it is a required deliverable of this gate, listed in H-011's scope item 5.
>
> This is a gate that would have passed for the wrong reason. `REPRODUCIBILITY.md` §10.

**Measurement**

> The full leak-fixture suite at every rung of H-011's capacity ladder: five modes
> (`none`, `label_in_features`, `target_encoding_on_all`, `train_test_overlap`,
> `scaler_fit_on_all`), 30 seeds (0–29), 30,000 synthetic bars — the harness that produced
> the 4-parameter baseline (`run_id` `5c6c585b-7531-48bd-945c-8c077b759a05`, commit
> `7d6ed38`). One re-measurement per rung, **under both fitting rules H-011 registers**
> (frozen 1,000 iterations, and the convergence stop).
>
> `run_type` is `harness_validation`. It carries no `hypothesis_id` for H-011 and is never
> evidence for it — it is a record of gate behaviour, as the 4-parameter baseline is.

**Pass condition — four parts, all required**

> | # | condition |
> |---|---|
> | i | **Capability.** `label_in_features` reaches BSS ≥ 0.99 at every rung, under both fitting rules. |
> | ii | **Reproduction.** C-0 under the *frozen* rule reproduces `RECORDED_MEAN_BSS` to within `1e-9` on all five modes. The degree-1 expansion is the identity, so anything else is a defect in the expansion, not a finding. |
> | iii | **Recording.** The tripping and silent sets are recorded per rung per fitting rule in `sensitivity.py`. |
> | iv | **Null re-measured.** The K-1 null (30 seeds, permuted labels, `LeakMode.NONE`) is re-measured at every rung under the rule H-011 will use, and K-1 is evaluated against *that* null. H-001's null is not reused. |
>
> **FAIL at a rung → K-1 halt at that rung.** H-011 may execute only at rungs that passed.
> A failed rung is recorded and excluded; it is not worked around, and the ladder is not
> shortened to avoid it.

**The capability test transfers. Here is what does not.**

> | item | transfers? | why |
> |---|---|---|
> | `label_in_features` ≈ 1.0 | **yes** | detecting a planted label is a floor any usable combiner meets at any capacity. This is the one H-001 §Estimator names, and it is the one that survives. |
> | K-6 clearance (1,364 ≥ 150) | **yes** | label-free and capacity-free; the decision grid is unchanged. Known before the run, as in H-003, H-007 and H-009. |
> | purge/embargo integrity | **yes** | a property of the split, not of the estimator. |
> | `scaler_fit_on_all` staying silent | **the reason, not the number** | it carries no label information at any capacity. Its *measured* −0.001390 is a property of a 4-parameter fit. |
> | `train_test_overlap` staying silent | **no** | `REPRODUCIBILITY.md` §6 says so by construction: undetectable at four parameters, detectable as capacity grows. At 56 parameters a fit may memorise 273 folded rows. |
> | `target_encoding_on_all` = +0.239781 | **no** (magnitude) | tripping is expected to transfer; the value is a property of the fit and is re-recorded. |
> | the K-1 null itself: mean −0.000855, CI upper −0.000577, max +0.000757 | **no** | an unregularised 56-parameter fit on permuted labels overfits the training folds. Its out-of-sample null is expected to be wider and more negative. Comparing a high-capacity edge against a low-capacity null is a leakage gate that has quietly stopped being one. |
> | H-001's `ACCEPTED` | **no** | `REPRODUCIBILITY.md` §6: "A combiner change without a recorded sensitivity re-measurement invalidates every subsequent K-1 pass." |
> | H-009's reliance on `logistic.py` being byte-identical | **no** | true for H-009, false here — see the guard gap above. |

**If `train_test_overlap` starts tripping**

> That is the gate becoming sharper, not a leak appearing in the pipeline. It is recorded
> as such **and then checked rather than assumed**: the Tier 1 purge/embargo integrity
> check is re-run and its result cited alongside. "The fixture leaks by construction and
> the real splits do not" is a claim with a test behind it; asserting it without citing the
> test is the §14 pattern again.

**`EVALUATION.md` §14 compliance — stated explicitly, because §14 requires it of every gate**

> | | |
> |---|---|
> | **adversarial fixture** | the five-mode leak suite. It exists (`evaluation/pipeline.py` `LeakMode`) and is reused unchanged. |
> | **external reference** | a second, independent solver for the same convex objective — **IRLS / Newton–Raphson**, test-only, never imported by `src`. The production gradient-descent fit must agree with it on fitted probabilities to `1e-6` max absolute deviation on a fixed synthetic fixture at every rung. |
>
> §14 requires at least one. This gate carries both, and the reason to carry both is that
> they fail differently: the fixture proves the gate can see a leak, the reference proves
> the *optimiser* found the solution it claims to have found. Neither substitutes for the
> other, and a larger combiner is exposed to the second failure in a way a 4-parameter one
> is not.
>
> IRLS is a genuine external reference and not a re-reading: it uses second-order
> information the production path never computes, so an error in the step rule, the
> learning rate, or the iteration budget surfaces as disagreement rather than as agreement
> on a wrong answer.

**Pre-committed interpretation**

> - **PASS:** H-011 executes, at the rungs that passed.
> - **FAIL at C-3 (H-011's primary rung):** H-011 does not execute at all. Halt and report
>   that the capacity question cannot be answered with a gate that cannot see a planted
>   leak at that capacity. This is not a negative result about capacity — it is no result.
> - **FAIL at a non-primary rung:** that rung is excluded from the reported profile and the
>   exclusion is stated in the result, not in an appendix.

--- RUN ---

- **Executed:** 2026-07-28, commit `4e3d9eb`, clean tree
- **Rows:** `runs/h010_frozen.json`, `runs/h010_convergent.json`
- **Registration precedes the code:** registration `312d9ba`, guard fix `8f3291a`,
  machinery `4e3d9eb`. §2 rule 1 satisfied.
- **Data:** 30,000 synthetic bars, seed 42; 834 pooled decisions across 5 folds; 30 seeds
  per configuration. `run_type: harness_validation`, no `hypothesis_id` — a record of gate
  behaviour, never evidence for H-001 or H-011.
- **Verdict:** **PASS at C-0, C-1, C-2. FAIL at C-3, C-4, C-5** — condition (iv) is not
  satisfiable there. **H-011 does not execute.**

**Condition (ii) — reproduction — holds, and the condition itself was mis-registered**

> C-0 under the frozen rule reproduces `RECORDED_MEAN_BSS` on all five modes:
> `none` `-0.001390`, `label_in_features` `+0.999984`, `target_encoding_on_all`
> `+0.239781`, `train_test_overlap` `-0.000901`, `scaler_fit_on_all` `-0.001390`. Identical
> at every recorded digit. The degree-1 expansion is the identity, so this was the outcome
> that would have indicted the expansion rather than taught anything, and it did not.
>
> **The registered tolerance was `1e-9` against a record carried to six decimal places.**
> That comparison cannot be made: the record does not hold the digits it would need. What
> is checkable — exact agreement at the recorded precision — holds. Recorded as a defect in
> this registration rather than silently reinterpreted.

**Condition (i) — capability — holds at every rung**

> `label_in_features` reaches `+0.999984` at 5, 8, 11, 21, 36 and 57 fitted parameters.
> The transferable requirement transferred.

**The frozen-rule table — 30 seeds, mean BSS, with fitted parameter count**

> | rung | p | `none` | `label_in_features` | `target_encoding_on_all` | `train_test_overlap` | `scaler_fit_on_all` |
> |---|---:|---:|---:|---:|---:|---:|
> | C-0 | 4 | −0.001390 | **+0.999984** | **+0.239781** | −0.000901 | −0.001390 |
> | C-1 | 7 | −0.001754 | **+0.999984** | **+0.239659** | −0.000949 | −0.001754 |
> | C-2 | 10 | −0.001850 | **+0.999984** | **+0.239460** | −0.000856 | −0.001850 |
> | C-3 | 20 | −0.002345 | **+0.999984** | **+0.239245** | −0.000666 | −0.002344 |
> | C-4 | 35 | −0.129314 | **+0.999984** | **+0.238961** | −0.130000 | −0.129032 |
> | C-5 | 56 | −0.390547 | **+0.999984** | **+0.084102** | −0.392723 | −0.390467 |
>
> Bold trips. The tripping set is `{label_in_features, target_encoding_on_all}` at every
> rung and the silent set is `{train_test_overlap, scaler_fit_on_all}` at every rung —
> **unchanged from four parameters to fifty-six.** The modes that append a column fit one
> parameter more than the rung declares, which is a property of the fixture and is recorded
> beside each row rather than absorbed.

**At what parameter count does `train_test_overlap` stop being silent**

> **It does not. Not at any point on this ladder.** That is the answer, and it is not the
> one the guard's own documentation predicted.
>
> `REPRODUCIBILITY.md` §6 says the leak "becomes detectable as capacity grows". Measured
> against the clean null at the same rung, it does:
>
> | rung | p | clean null | `train_test_overlap` | excess |
> |---|---:|---:|---:|---:|
> | C-0 | 4 | −0.001390 | −0.000901 | **+0.000489** |
> | C-1 | 7 | −0.001754 | −0.000949 | **+0.000805** |
> | C-2 | 10 | −0.001850 | −0.000856 | **+0.000994** |
> | C-3 | 20 | −0.002345 | −0.000666 | **+0.001679** |
> | C-4 | 35 | −0.129314 | −0.130000 | −0.000686 |
> | C-5 | 56 | −0.390547 | −0.392723 | −0.002176 |
>
> The excess rises monotonically from 4 to 20 parameters and roughly triples. The mechanism
> §6 describes is real and is now measured rather than asserted. **It is also two orders of
> magnitude short.** At 20 parameters the leak shows up as `+0.00168` against a trip
> threshold of `0.05` — a factor of thirty — and above 20 parameters the excess turns
> *negative*, because the estimator has stopped fitting.
>
> **K-1's known blind spot is not closable by capacity within this estimator family.**
> Closing it needs a different family — the gradient-boosted stacker `EVALUATION.md` §2
> rung 7 names — and that is a different change requiring its own ID. The blind spot stays
> open, and it stays open for a reason that is now measured instead of assumed.

**Why C-4 and C-5 fail, and why "K-1 passed" there means nothing**

> At C-4 and C-5 the clean null collapses to `−0.129` and `−0.391`. K-1's three registered
> conditions all hold at those numbers — CI upper below ε, no seed reaching 0.05, median
> below zero — so the gate returns **PASS**.
>
> **It is a vacuous pass.** The gate is satisfied because an unregularised 35- and
> 56-parameter fit at a thousand gradient steps produces out-of-sample probabilities worse
> than climatology by a wide margin, not because no leak is present. A gate that passes
> because the instrument stopped working is `REPRODUCIBILITY.md` §10 exactly: a gate that
> passes for a reason nobody can state is not a working gate. It is recorded here as a pass
> that must not be cited.
>
> Corroborating, from the same run: `target_encoding_on_all` falls from `+0.239` to
> `+0.084` at C-5 — the one leak a low-capacity linear model reads most easily is becoming
> hard to read, within 1.7x of the trip threshold. The instrument is degrading, and it
> degrades toward silence, which is the direction that hides failures.

**Condition (iv) — the null re-measured under the rule H-011 will use — cannot be met**

> The convergence rule is `grad_inf <= 1e-6`, cap `1e6`. Measured on the largest training
> pool (fold 4, n = 25,929), with the Gram condition number that explains it:
>
> | rung | p | cond(gram) | gradient at 1e3 | 1e4 | 1e5 | reaches 1e-6? |
> |---|---:|---:|---:|---:|---:|---|
> | C-0 | 4 | 1.21e+01 | — | — | — | **yes, 337 iterations** |
> | C-1 | 7 | 5.41e+02 | 1.33e-04 | — | — | **yes, 8,664** |
> | C-2 | 10 | 4.52e+03 | 1.86e-04 | 3.52e-06 | — | **yes, 17,618** |
> | C-3 | 20 | 1.04e+06 | 2.42e-04 | 1.46e-04 | 4.62e-05 | not by 1e5 |
> | C-4 | 35 | 1.82e+08 | 1.63e-01 | 1.57e-01 | 1.51e-01 | **stalled** |
> | C-5 | 56 | 2.87e+10 | 2.89e-01 | 2.80e-01 | 2.74e-01 | **stalled** |
>
> The condition number of the polynomial design rises by nine orders of magnitude across
> the ladder. First-order descent at a fixed step needs `O(kappa)` iterations, and at C-4
> the gradient moves from `0.1634` to `0.1510` across a hundredfold increase in iterations.
> That is not slow convergence. It is a stall.
>
> **C-3 is different and the difference was measured rather than extrapolated.** At the
> registered `1e6` cap on the *smallest* fold (n = 9,929) it converged: **533,168
> iterations, gradient `1.0000e-06`, 216 s**. So C-3 is reachable — and reaching it for the
> full suite is 5 folds x 5 modes x 30 seeds at that cost, on the order of **150 hours for
> one rung**. Reachable and unaffordable are different findings and are reported as
> different findings. The largest-fold measurement at the full cap was started and stopped
> to free the machine for the sweep; it is not reported as completed.

**A second mechanism, independent of conditioning, that blocks (iv) at every rung**

> The convergent sweep was launched for C-0, C-1 and C-2 — the rungs the conditioning
> analysis says are reachable. It completed **one cell**: `C-0 / none`, mean BSS
> `-0.001389` against the frozen rule's `-0.001390`, converged, 13.1 s. It then spent
> twelve minutes on `C-0 / label_in_features` without finishing, and was stopped and
> measured directly instead.
>
> | C-0, fold 0 | cond(gram) | iterations to `1e-6` | time, one fold |
> |---|---:|---:|---:|
> | clean design | 1.209e+01 | **314** | 0.0 s |
> | + planted label | 1.235e+01 | **426,723** | **72.7 s** |
>
> **The conditioning is the same. The cost is 1,359x.** The cause is not the Gram matrix —
> it is **separability**. Appending the label makes the training set perfectly separable,
> so the unpenalised optimum is at infinity and the `1e-6` ridge only pulls it back to a
> very large finite value that first-order descent approaches asymptotically. The gradient
> falls `2.0e-03 -> 1.96e-04 -> 1.49e-05 -> 1.0e-06` across three decades of iterations,
> and converges only in the last decade before the cap.
>
> The capability fixture is therefore ~3 hours per rung under the convergence rule at the
> **cheapest** rung, before any conditioning problem is reached. **Condition (iv) is
> unaffordable at every rung on the leak fixtures and unreachable at C-3 and above on all
> of them.** Two independent mechanisms, neither named in the registration, each sufficient
> on its own.
>
> Both are properties of pairing a first-order optimiser with a fixed step size to
> objectives whose optima are either ill-conditioned or at the boundary. Neither is a
> property of capacity, which is what H-011 set out to vary.

**What this does to H-011**

> H-011's primary rung is C-3 and its primary fitting rule is the convergence stop. **That
> combination is not executable.** Under the pre-committed interpretation above, the FAIL
> branch at C-3 is active: **H-011 does not execute at all.**
>
> The correct action is the registered one. H-011 is not rerun at C-2 to get a number, and
> its primary rung is not moved: choosing the rung after seeing which ones are affordable
> is `RESEARCH.md` §5.2, and the fact that the constraint is computational rather than
> statistical does not change what selecting on it would be. A registration that turns out
> to be unexecutable is corrected by a **new hypothesis**, registered before it runs.
>
> H-011 stays `REGISTERED` and unexecuted. It is not `VOID`: nothing about it was
> invalidated, and its `N_claims` draw stands — the question was asked, and the answer is
> that this instrument cannot answer it.

**What was learned that no registration anticipated**

> The capacity axis was chosen because it was the cheap one: same features, same label,
> same optimiser, one number changing. It is cheap in every respect except the one that
> turned out to bind. **Raising the parameter count of a polynomial design raises the
> condition number far faster than it raises the parameter count** — 4 to 56 parameters is
> 14x; 12 to 2.9e10 in conditioning is nine orders of magnitude — and a first-order
> optimiser is the wrong instrument at the far end of that. Nothing in the registration
> mentioned conditioning. It is the constraint that decided the run.
>
> The registration reasoned carefully about *one* way the optimiser could produce a fluent
> wrong answer — a fixed budget silently underfitting — and built a VOID condition for it.
> That reasoning was right, and the measurement confirms it: at C-3 the frozen fit
> demonstrably disagrees with IRLS. What it did not anticipate is that the fix has its own
> failure modes, that there are two of them, that they are unrelated to each other, and
> that neither is about capacity. **Registering a guardrail against a known failure is not
> the same as knowing the instrument**, and the gap between those two is where this run
> ended up.

**Recorded for whatever replaces H-011**

> Not amendments — H-011 is not edited. These are the measured facts a successor
> registration would have to answer, written down while they are fresh:
>
> 1. A polynomial basis on three features is a badly conditioned capacity axis. Any
>    successor either orthogonalises the basis, or uses a second-order solver, or does not
>    use polynomials.
> 2. The capability fixture is separable by construction, so *any* convergence criterion
>    stated as a gradient tolerance is expensive on it. A successor states its capability
>    criterion in a form separability does not blow up — a fitted-probability threshold, or
>    a tolerance on the *change* in fitted probabilities rather than on the gradient.
> 3. The frozen rule ran the entire ladder in under an hour and reproduced the recorded
>    baseline exactly. It is a usable instrument for what it measures; what it cannot do is
>    support a claim about capacity, because above 20 parameters it stops fitting.

---

### H-011 — Capacity alone: is the four-parameter combiner the binding constraint?

- **Registered:** 2026-07-28 UTC
- **Class:** **claim** — counts toward `N_claims`, taking it **4 → 5**
- **Status:** REGISTERED
- **Order:** after H-010 passes. Before any feature-set change.

**Claim**

> Holding the three registered features, the registered direction label, the registered
> folds and the registered snapshot fixed, and increasing **only** the combiner's parameter
> count from 4 to 20, out-of-sample pooled Brier Skill Score improves by at least **+0.010**
> absolute, the per-decision Brier improvement is positive at one-sided `p ≤ 0.01`, and at
> least **half** of the improvement is resolution rather than reliability.

**What this separates, and what it deliberately does not**

> It removes explanation **B** from §6's list, in one direction or the other. It does not
> touch **A** or **C**, and no result here licenses a statement about either.
>
> If BSS moves materially with capacity alone, the four-parameter estimator was the binding
> constraint, and **slice 1 is answering the wrong question** — the right next question
> would be capacity, not breadth. If it does not move, capacity is excluded over the range
> tested and slice 1 becomes interpretable, because a null result there can no longer be
> explained by the combiner.

**Held fixed / changed**

> | | |
> |---|---|
> | features | `log_return_24`, `realized_vol_24`, `range_position_48` — **exactly three, unchanged** |
> | label | 24-bar **direction**, materiality floor ε = 0.01 (H-001). Not H-009's volatility label. |
> | window | `window_start` 2015-09-11 (H-006), snapshot `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6` |
> | folds | 5 walk-forward, `FIRST_TEST_FRACTION` 0.50, 24-bar decision spacing, purge + embargo (H-001) |
> | n | 1,364 pooled decisions, 272–273 per fold — **identical rows, identical order, in every arm** |
> | metric | out-of-sample pooled BSS on true labels — H-001's unshuffled control, same code path |
> | **changed** | **the number of free parameters in the combiner. Nothing else.** |

**The capacity ladder — fixed before running**

> The same `LogisticRegression`, the same convex objective, the same optimiser, fed a
> deterministic polynomial basis expansion of the same three columns.
>
> | rung | design matrix | parameters | rows per parameter |
> |---|---|---:|---:|
> | **C-0** | degree 1 — H-001 unchanged | **4** | 8,047:1 |
> | C-1 | + pure squares | 7 | 4,598:1 |
> | C-2 | full degree 2 | 10 | 3,219:1 |
> | **C-3** | **full degree 3** | **20** | **1,609:1** |
> | C-4 | full degree 4 | 35 | 920:1 |
> | C-5 | full degree 5 | 56 | 575:1 |
>
> 14× capacity across the ladder. The training pool is 32,188 rows (H-001's split table),
> so **sample size is not the binding constraint at any rung** — the same argument H-001
> used to dismiss "more training data" as a reason for a later split applies here in
> reverse. The ladder stops at 56 because of estimator-family purity, not data.

**Why a basis expansion is "the same features"**

> No new measurement enters. Every column is a deterministic, label-free, pointwise
> function of the three registered features on the same row. What grows is the function
> class over them, which is the definition of capacity.
>
> Stated the other way, because it is the objection a reader should raise: the *design
> matrix* does change, and someone could call C-3 "twenty features". The distinction that
> matters is that no new information about the market is introduced, so a BSS gain cannot
> be attributed to data the four-parameter model did not have. That is exactly the
> attribution slice 1 cannot make.

**Why the estimator family does not change**

> A tree ensemble or an MLP would raise capacity further and faster. Both would also change
> the optimiser, the initialisation, the non-convexity of the objective, and the seed
> surface — four changes bundled with the one under test, violating §2 rule 4, and leaving
> any difference unattributable in precisely the way H-007 was designed to avoid.
>
> A non-linear estimator family is a **separate hypothesis with its own ID**. It is
> registered only if H-011 returns "did not move" at C-3 *and* the profile across C-0…C-5
> is flat — i.e. only if the polynomial family has been shown to be an inadequate probe
> rather than an adequate one that found nothing.

**What is NOT changed, and why each would have been a second change**

> | | |
> |---|---|
> | regularisation | **none added.** An L2 term is a hyperparameter, and a hyperparameter is a surface to tune until the answer is agreeable. The higher rungs are therefore unregularised, which is a real cost — see the pre-committed reading of a *negative* ΔBSS. |
> | standardisation | the existing `Standardizer`, **fit on training folds only**, applied to the expanded matrix. Fitting it on all rows is `scaler_fit_on_all`, a registered leak mode. |
> | learning rate | 0.5, unchanged. |
> | bootstrap | block 10, sensitivity at 1 and 25, 10,000 resamples, seed 1337 — H-003 §F, inherited unchanged, as H-009 §C inherited it. |
> | decision grid | unchanged, and label-free, so K-6 clearance (9.1×) is known before the run. |

**The iteration budget is a convergence parameter, not a capacity parameter**

> This is the single most likely way this hypothesis produces a fluent wrong answer, so it
> is registered as a design decision rather than left as an implementation detail.
>
> 1,000 iterations at learning rate 0.5 suffices for 4 parameters. On 56 correlated
> polynomial terms it may not converge — and a non-converged fit *underfits*, which reads
> as "capacity did not help". The conclusion "the four-parameter combiner was not the
> binding constraint" would then be an artefact of the optimiser budget, internally
> consistent and wrong: `EVALUATION.md` §14's pattern, in a new instrument.
>
> **Primary path — convergence stop, applied at every rung including C-0.** Iterate until
> the gradient infinity-norm at the current parameters is ≤ `1e-6`, cap `1e6` iterations.
> Report iterations used per rung per fold. This removes optimisation error from the
> comparison so that capacity is the only difference.
>
> **Secondary path — frozen 1,000 iterations at every rung.** Reported alongside, so the
> H-001-comparable number exists and so the difference between the two paths is visible
> rather than absorbed.
>
> **The C-0 convergence gap is a first-class output, not a footnote.** If
> `|BSS(C-0, converged) − (−0.006766)|` exceeds the did-not-move band, then part of
> H-001's recorded control number was optimiser truncation. That is **appended to H-001,
> never edited into it**, and reported in H-011's result at the top rather than in a
> caveat — the treatment H-003 §K required of the cost comparison, for the same reason.
>
> **VOID condition.** If the cap is reached without the gradient tolerance being met at any
> rung the primary statements are evaluated at, the run is **VOID, not negative**. A fit
> that did not converge cannot support "capacity is not the constraint".

**The primary rung is designated in advance: C-3**

> All six rungs are run and the full profile is reported. **Only C-3 supplies the verdict.**
>
> C-3 rather than C-5 for a reason available before the run: degree 3 is the lowest degree
> at which a three-way interaction among three features exists at all. C-2 can represent
> every pairwise interaction; only C-3 and above can represent `x₁·x₂·x₃`. C-3 is therefore
> the smallest rung that can express *every* interaction among the registered features,
> which makes it the smallest rung whose null result is informative.
>
> **Rung shopping is structurally unavailable, not merely discouraged.** If C-3 lands in
> the did-not-move band and a higher rung is materially positive, that is a **new
> hypothesis with a fresh draw against `N_claims`**, not a result of H-011. The profile is
> reported in full so the reader sees the higher rung; H-011's verdict does not move.

---

**Three pre-committed statements. Three metrics. Three thresholds.**

> **This is the correction H-009 §J earned.** H-009 registered sign and attribution and
> registered nothing about magnitude, then the verdict turned on magnitude: `+0.024157`
> was a real, significant, mechanistically-predicted effect that failed a threshold set for
> a different purpose. Its own verdict block records the defect — "'Does the feature layer
> work' and 'does it reach BSS 0.05' were bound together as one question when they are
> two."
>
> Below, each question has its own metric, its own number, and its own outcome. They can
> disagree, and the joint table says what it means when they do. **No single threshold can
> decide more than one of them.**

**Statement 1 — MAGNITUDE. Did it move enough to matter?**

> - **Metric:** `ΔBSS = BSS(C-3) − BSS(C-0)`, out-of-sample pooled, both under the primary
>   convergence path.
> - **Material threshold:** `ΔBSS ≥ +0.010`.
> - **Did-not-move band:** `|ΔBSS| < max(0.002, the C-3 K-1 null's largest absolute
>   excursion as measured by H-010)`. The rule is fixed here; the number is fixed by a gate
>   that runs first, so it is not shoppable in either direction.
> - **Middle zone:** everything between.
>
> **Why +0.010, and why a difference rather than a level.** The question is the attribution
> of a *change*, so the threshold is on the change. Requiring the change alone to clear
> K-3's 0.05 trading-materiality floor would repeat H-009 §J's defect with the inequality
> pointing the other way. Four anchors, stated so a reader can substitute their own:
> 1. ~13× the largest single-seed excursion of the K-1 null at 4 parameters (+0.000757), so
>    it cannot be produced by the noise floor the gate measured.
> 2. 20% of `K-3`'s 0.05 — the project's own registered floor for a BSS that means anything.
> 3. Against C-0 at −0.006766 it means the larger combiner does not merely recover the
>    four-parameter deficit but **crosses zero into positive skill**.
> 4. ~41% of `+0.024157` — the only real effect this feature set has been shown to carry,
>    measured by H-009 with the *same* features and the *same* four parameters.

**Statement 2 — SIGN. Is the move distinguishable from zero?**

> - **Metric:** per-decision Brier improvement
>   `bᵢ = (f_{C-0,i} − oᵢ)² − (f_{C-3,i} − oᵢ)²`, positive when the larger combiner is
>   better. Paired by construction: identical decisions, folds, labels, rows and order —
>   capacity is the only difference. The H-003/H-007 paired design in probability space,
>   and the same statistic H-009 §E used.
> - **Test:** stationary bootstrap of `mean(b)`, block 10, sensitivity reported at 1 and 25,
>   10,000 resamples, seed 1337. One-sided `H₁: mean(b) > 0`.
> - **Threshold:** `p ≤ 0.01` — the Benjamini–Hochberg rank-1 critical value at
>   `N_claims = 5`. See §9 below, including the step-up route to 0.03 that is refused in
>   advance.
> - **Block sensitivity is reported and is not permitted to be silent.** H-009's §9
>   consequence turned on the fourth decimal at block 25 and its entry says so. If the
>   verdict here differs across blocks 1, 10 and 25, the result states that it does and
>   reads as holding at the registered block only.

**Statement 3 — ATTRIBUTION. Is the move discrimination, or is it calibration?**

> - **Metric:** Murphy decomposition, `EVALUATION.md` §3.4, `BS = Reliability − Resolution
>   + Uncertainty`. Uncertainty is a property of the labels alone and is identical across
>   rungs, so `ΔBS = ΔReliability − ΔResolution`.
>   **Resolution share** `= ΔRes / (ΔRes − ΔRel)`, the resolution gain as a fraction of the
>   total Brier improvement.
> - **Threshold:** resolution share **≥ 0.50**.
> - **Binning, registered before the run:** 10 equal-width bins of forecast probability on
>   [0, 1]. The equal-count (decile) version of `EVALUATION.md` §3.3 is reported as a
>   sensitivity, not as the primary.
>
> **Why this is a separate question and not a refinement of the other two.** A larger
> combiner can improve Brier score by fitting the *base rate* more sharply while
> discriminating no better — §3.4: "Low resolution means there is no signal, and no amount
> of calibration will create one." That is the H-007 finding restated in probability space:
> the signal arm's 56.2% long was the base rate, and the entire difference was attributable
> to it. **A capacity gain that is all reliability is the same confound wearing different
> clothes, and it must not be able to pass this hypothesis.**

**Registered prediction — reported, explicitly not a pass condition**

> In H-009 §G's pattern, so it can be scored rather than recalled:
>
> **Predicted: `ΔBSS` at C-3 lands in the did-not-move band, and capacity is excluded.**
> Grounds: H-009 measured the same four parameters on the same features extracting
> `+0.024157` at `p = 0.0150` on a different label. A hypothesis class that found real
> structure when it was there is unlikely to be the thing hiding structure when it is not.
>
> **This prediction has no bearing on the verdict**, which is decided only by the three
> statements above. It is recorded so that a confirmation is worth something and a
> refutation is visible — and because a registration whose author expects a null result is
> the registration most at risk of an under-powered instrument passing unexamined. That
> risk is what the convergence guardrail and H-010 are for.

---

**The joint reading — pre-committed, so no combination has to be interpreted afterwards**

> | magnitude | sign | attribution | reading | action |
> |---|---|---|---|---|
> | ≥ +0.010 | `p ≤ 0.01` | share ≥ 0.50 | **Capacity was the binding constraint.** | **ACCEPTED.** Slice 1 as proposed is withdrawn — it is the wrong question. Register the capacity question properly instead. |
> | ≥ +0.010 | `p ≤ 0.01` | share < 0.50 | Capacity bought **calibration, not discrimination**. | **REJECTED.** The premise of slice 1 is unsupported; nothing here says the features carry direction. Report the reliability gain as the finding it is. |
> | ≥ +0.010 | `p > 0.01` | any | A material point estimate the data cannot distinguish from zero. | **REJECTED**, per template §3: AMBIGUOUS defaults to REJECT. Report ΔBSS and its CI; do not describe it as a trend. |
> | 0.002 … 0.010 | `p ≤ 0.01` | any | Capacity is a **contributing but non-binding** constraint. | **REJECTED** as a claim. Slice 1 proceeds, and every result it produces is reported **net of a capacity term of the measured size**, stated in the result. |
> | did-not-move band | any | any | **Capacity is excluded over the range tested.** | **REJECTED.** Explanation B is removed from §6's list. Slice 1 becomes interpretable and is registered next. |
> | `ΔBSS ≤ −0.002` | — | — | The larger combiner is **worse out-of-sample**: variance, not absence of signal. | **REJECTED**, and the reading is stated as variance. An unregularised 20-parameter fit degrading is what overfitting looks like; it is **not** evidence that the features are empty and must not be reported as if it were. |

**§9 — `N_claims` and the critical value, stated before the run**

> Registering this claim moves `N_claims` from **4 to 5** (H-003, H-004, H-007, H-009,
> H-011). Under `EVALUATION.md` §9, Benjamini–Hochberg at α = 0.05:
>
> | rank k | critical `0.05 × k/5` |
> |---|---|
> | **1** | **0.0100** |
> | 2 | 0.0200 |
> | 3 | 0.0300 |
> | 4 | 0.0400 |
> | 5 | 0.0500 |
>
> **What registering this costs, before it runs — computed, not asserted.** At `m = 4` the
> family currently rejects at `k = 2`: H-009 at `0.0150` and H-003 at `0.0204 ≤ 0.025`. At
> `m = 5` with H-011 unrun, the available `p` are `0.0150`, `0.0204`, `0.5041`; rank 1 needs
> `≤ 0.0100`, rank 2 needs `≤ 0.0200`, rank 3 needs `≤ 0.0300`, and **none holds.**
> **Registering H-011 removes the family's current rejection.** H-003 loses the §9 clearance
> it gained hours ago and H-009 loses its own — at the moment of registration, before any
> data is touched.
>
> That cost is accepted and is recorded here rather than discovered later. It is also
> largely nominal: H-009 was rejected on its primary threshold, not on §9, and H-003's
> directional reading was withdrawn on H-007's substantive grounds. Neither depends on the
> clearance being lost. **This is the third time the registry has visibly weakened an
> existing result by asking a new question, and it is the mechanism working.**
>
> **The step-up route that is refused in advance.** With `0.0150` and `0.0204` in the
> family, the arithmetic admits H-011 at any `p ≤ 0.03`: for `p* ≤ 0.0300` the sorted first
> three are within `{0.0150, 0.0204, p*}` and `p₍₃₎ ≤ 0.0300`, so `k = 3` and all three are
> rejected. **H-011 will not be reported as clearing §9 by that route.** Being carried over
> the line by the p-values of a claim rejected on magnitude and a claim whose reading is
> withdrawn is not a correction doing its job. **The registered threshold is `p ≤ 0.01`**,
> written here, before the run, so that a `p` of 0.02 cannot afterwards be presented as
> clearing.
>
> **The symmetric consequence, also pre-committed.** If H-011 returns `p ≤ 0.03`, the
> step-up rejects H-003 and H-009 alongside it and both clear §9 again. **That restores
> nothing.** H-003's reading was withdrawn on a confound; H-009 was rejected on a
> magnitude threshold. A correction they pass later cannot answer either. This is recorded
> now so it cannot be discovered later — as H-009 §D recorded the same thing about H-003
> and was proved right.

**Guardrails**

> | | |
> |---|---|
> | K-1 | via H-010, at the rung used, against the null measured at that rung. |
> | K-6 | 1,364 ≥ 150, cleared 9.1×. Label-free, so known now. |
> | convergence | gradient ∞-norm ≤ `1e-6` per fold per rung, else **VOID**. |
> | external reference | IRLS agreement to `1e-6` on the fixed fixture, per H-010 and `EVALUATION.md` §14. |
> | C-0 identity | C-0 under the frozen path must reproduce H-001's `−0.006766` exactly. If it does not, the expansion is defective and the run is VOID before any rung is read. |
> | rung selection | none. C-3 is designated above and the verdict does not move. |

**Sample size expected**

> 1,364 pooled decisions, 272–273 per fold. Identical in every arm by construction.

**Required scope, registered before it is built**

> As H-003 §I did, so the build cannot quietly become the hypothesis:
>
> 1. Deterministic polynomial basis expansion — pure, label-free, pointwise. **It ships with
>    `tests/features/test_polynomial_expansion.py` asserting truncated-history equality.**
>    A pointwise transform of same-row features cannot leak across time; "cannot" is the
>    word every defect in `EVALUATION.md` §14 was fluent about, so the test is written
>    anyway. Hard Rule 1 admits no exception.
> 2. Murphy decomposition in `src/metrics/`, with the identity `BS = Rel − Res + Unc`
>    asserted to `1e-12`.
> 3. Convergence instrumentation: the gradient infinity-norm exposed on the fitted object,
>    plus the convergence-stop fitting rule alongside the frozen one.
> 4. IRLS reference solver, **test-only**, never imported by `src` — with a guard test
>    asserting that, in the pattern of
>    `test_no_rung_has_been_smuggled_into_the_evaluation_path`.
> 5. **`sensitivity.py` keyed on effective parameter count, not on `logistic.py`'s AST
>    alone** — the gap H-010 records. Per-rung recorded constants.
> 6. `scripts/run_h010.py`, `scripts/run_h011.py`.
> 7. `test_c0_reproduces_h001_exactly`.

**Constants introduced — forced, derived, judgement**

> Thirteen, of which **eight are judgement**. H-003 §L's and H-009 §I's accounting,
> continued.
>
> | constant | value | class |
> |---|---|---|
> | BH threshold | `p ≤ 0.01` | **forced** — rank 1 at `m = 5`, α = 0.05, `EVALUATION.md` §9 |
> | bootstrap block / resamples / seed | 10 / 10,000 / 1337 | **forced** — H-003 §F |
> | standardisation fit on train only, post-expansion | — | **forced** — the alternative is a registered leak mode |
> | no regularisation | — | **forced** — §2 rule 4, one change |
> | did-not-move band | `max(0.002, C-3 null max excursion)` | **derived** — rule registered here, value set by H-010 |
> | ladder degrees | {1, 2ᴰ, 2, 3, 4, 5} | judgement |
> | primary rung | C-3 | judgement — reasoned above, still judgement |
> | material threshold | +0.010 | judgement — four anchors given |
> | the floor inside the derived band | 0.002 | judgement |
> | resolution share | ≥ 0.50 | judgement |
> | decomposition bins | 10, equal-width | judgement |
> | gradient tolerance | `1e-6` | judgement |
> | iteration cap | `1e6` | judgement |
>
> **If the verdict lands within one band-width of any threshold in either direction, the
> result names which of the eight it is most sensitive to**, as H-003's result was required
> to. A verdict that turns on an unmeasured judgement call is a different kind of result
> from one that does not.

**What a PASS licenses, and what it does not**

> A PASS licenses **registering the capacity question properly** — a larger hypothesis class
> at fixed features — and withdraws slice 1 as currently scoped.
>
> It licenses **nothing about explanations A or C.** It does not say the features carry
> direction; it says four parameters could not express what three features hold. It does not
> say `H = 24` is learnable. It does not license a trading claim of any kind: this is a
> probability-quality hypothesis measured on `EVALUATION.md` §3, no cost model is involved,
> and no rung of §2's ladder is touched. **The ladder is still halted at rung 2.**

**2026-07-28 — ABANDONED. Not answered. Status stays `REGISTERED`.**

> The capacity question is abandoned as a line of inquiry. This block records that it was
> abandoned, why, and what remains untested, because the failure mode it guards against is
> a later reader collapsing "abandoned" into "excluded".
>
> **Capacity remains untested.** H-011's three pre-committed statements — magnitude, sign,
> attribution — were never evaluated. No number exists. If a later feature sweep returns a
> null and someone raises the combiner-size objection, **the honest response is that it was
> never tested, and this is why.** A retrofitted claim that capacity was excluded would be
> false.
>
> **What made it unanswerable by this route.** H-010 measured that the registered
> convergence rule is unreachable at C-3, C-4 and C-5 — the Gram condition number of the
> polynomial design rises `1.21e+01` to `2.87e+10` across the ladder and first-order descent
> stalls — and unaffordable on the capability fixture at every rung including C-0, where
> separability costs 426,723 iterations against 314 at identical conditioning. H-011's
> primary rung under its primary rule is not executable.
>
> **Why it is abandoned rather than re-registered with a second-order solver.** Three
> reasons, in the order they weigh:
>
> 1. **Three columns is a very small hypothesis class regardless of what is fitted over it.**
>    A larger function class over the same three features is a narrow question, and both
>    H-011's own registered prediction and H-009's positive control — four parameters
>    extracting `BSS +0.024157` at `p = 0.0150` on the volatility label — point to a null.
> 2. **Its remaining value was political, not epistemic.** The case for running it was that
>    a null would remove the "your combiner was too small" objection before a feature sweep
>    raised it. Pre-empting an objection is not evidence, and it does not justify a
>    registration and a gate.
> 3. **It would have spent an independent anchor.** The IRLS solver is currently in
>    ``tests/`` and never imported by ``src``, which is what makes it an *external*
>    reference under `EVALUATION.md` §14. Promoting it into the production path inverts its
>    role: the frozen gradient path becomes the reference instead, and the second-order
>    anchor is gone. Five instrument defects have been found in this project and **three had
>    a self-check that agreed with them because it shared their assumption.** Independent
>    anchors are the scarcest resource here, and spending one on a question whose answer is
>    already expected is the worst available trade.
>
> **`N_claims` is unchanged at 5.** H-011's draw stands. That is the cost of having
> registered it, and the registry records what was done rather than what was completed —
> the same principle under which H-003 keeps `Status: ACCEPTED` for a reading that has been
> withdrawn. Abandoning a hypothesis does not refund its draw; if it did, the denominator
> would be a record of successes.
>
> **What the next slice must not do.** It must not cite this entry as evidence about
> capacity in either direction, and it must not quietly widen the feature set *and* the
> combiner at once — the confound H-011 existed to remove is still there, unremoved, and
> now known to be unremovable cheaply.

**2026-07-28, later — CORRECTION to the block above. The tractability argument was wrong.**

> H-012 measured what H-010 could not: **eleven parameters of real features converge at a
> thousand gradient steps**, worst gradient infinity-norm `8.5e-07` to `1.6e-06` across
> three horizons. H-010 measured twenty parameters of *polynomial* design leaving the
> gradient at `2.4e-04`, and thirty-five stalling at `0.15`.
>
> **The optimiser failure was a property of the polynomial basis, not of parameter count.**
> A design matrix of genuinely different measurements is well-conditioned where a basis
> expansion of three columns is not.
>
> **What that falsifies in the block above:**
>
> - "What made it unanswerable **by this route**" was correctly scoped and stands — but the
>   surrounding framing implied the cost was intrinsic to raising capacity. It was not.
>   Capacity was not computationally unanswerable in general. It was unanswerable **by the
>   polynomial route**, which is a much narrower statement.
> - "now known to be unremovable cheaply", in the last paragraph, is **false as written**.
>   The confound is removable at ordinary cost by a well-conditioned design; H-011 chose an
>   ill-conditioned one.
>
> **What it does not falsify, and what the abandonment now rests on.** Reason 1 — *three
> columns is a very small hypothesis class regardless of what is fitted over it* — is
> untouched, and it was always the load-bearing one. Reasons 2 and 3 are untouched.
> **The abandonment stands on the size of the hypothesis class, not on tractability.**
> Anyone citing this entry should cite that ground and not the other.
>
> Recorded as a correction rather than an edit, per §2 rule 3's principle: the original
> reasoning is left visible so that the error is part of the record rather than absent
> from it.

---

### H-012 — Does any deterministic feature set carry directional information at this horizon?

- **Registered:** 2026-07-28 UTC
- **Class:** **claim** — counts toward `N_claims`, taking it **5 → 6**
- **Status:** **REJECTED** — all four no-conditions hold, at every horizon.
  (Corrected 2026-07-28 at close-out, same defect as H-009's: the header was never
  updated after the run.)

**Claim**

> A ten-feature deterministic design — the three registered features plus seven added on
> stated priors — extracts out-of-sample pooled `BSS >= +0.010` on the direction label, with
> the per-decision Brier improvement over the three-feature baseline positive at one-sided
> `p <= 0.00833`, at at least one of the registered horizons, and the improvement is not
> attributable to long bias.

**One claim, not seven**

> The seven features are seven **priors**, not seven questions. Registering them
> individually would take `N_claims` to 12 and the rank-1 critical value to `0.00417`,
> inflating the denominator with tests that are not independent questions. They enter as one
> claim with a **mandatory ablation** — which is what keeps the denominator honest without
> pretending the ablation arms are free. The ablation is a decomposition of one result, not a
> family of results, and no ablation arm may be reported as a claim in its own right.

---

#### §A. The four no-conditions, registered before any feature was named

> Written before the feature set so the criteria could not be shaped around the candidates.
> **I conclude the answer is no if all four hold.**
>
> | # | condition | threshold |
> |---|---|---|
> | i | **Magnitude.** Out-of-sample pooled BSS on true labels does not clear the floor | `BSS < +0.010` |
> | ii | **Sign.** Per-decision Brier improvement over the three-feature baseline is not distinguishable from zero | `p > 0.00833`, one-sided |
> | iii | **Horizon.** It fails at every registered horizon | at `H = 4`, `24` and `120` |
> | iv | **Attribution.** Nothing that clears (i) and (ii) survives the always-long comparison | see §E |
>
> **Why `+0.010`:** one fifth of K-3's `0.05` floor, the same materiality anchor H-001's ε
> uses, and an order of magnitude above the largest single-seed excursion of the K-1 null.
>
> **What does not count as "no":** a null at one horizon only; a null with a non-converged
> fit; a null where the capability test has not passed. Those are non-results. H-010 is the
> reason that distinction is now explicit rather than assumed.
>
> **What this cannot claim either way:** whether a larger combiner would have found more.
> H-011 is abandoned and capacity is untested. That stays true whatever this returns.

#### §B. The feature set — seven priors, stated before any number

> **Constraint honoured: nothing session-relative**, while R-001 is open. Every feature is a
> pure function of OHLCV and tick volume over a backward window. None reads a session
> boundary, a time of day, or anything derived from the era calendar. `session_relative`
> is `False` on all seven and `tests/test_causality.py` asserts it.
>
> Two pairs are deliberately included together. A set containing momentum but not reversal
> is a bet on which of two documented and opposite effects dominates; including both makes
> it empirical.
>
> | # | feature | captures | prior — why it might carry direction |
> |---|---|---|---|
> | 1 | `log_return_120` | momentum, weekly | Time-series momentum is the most replicated directional effect in commodities and FX. `log_return_24` tests one scale; if trend persistence exists here its natural scale is days-to-weeks. |
> | 2 | `log_return_480` | momentum, monthly | Same prior, longer. Two scales test whether the *horizon of the predictor* matters, which one scale cannot. |
> | 3 | `vol_scaled_return_120` | momentum per unit risk | `log_return_120 / realized_vol_120`. Standard in managed-futures construction. Not redundant with 1: it **re-ranks** past moves rather than rescaling them, so a large move in a calm regime outranks a larger move in a violent one. |
> | 4 | `reversal_4` | short-horizon overreaction | The opposite prior to 1-3, at a shorter scale: liquidity provision after a sharp move. Documented intraday-to-daily in many markets. Included so the set is not a one-sided bet on persistence. |
> | 5 | `atr_distance_480` | trend state | `(close - SMA(480)) / ATR(14)`. The classic trend-following state variable. Unlike `range_position_48`, which is bounded and local, this is unbounded and slow: it distinguishes "far above a slow anchor" from "high within a recent range". |
> | 6 | `drawdown_from_max_480` | proximity to highs | Gold's behaviour near multi-week highs plausibly differs from mid-range behaviour — breakout dynamics, and the asymmetry commodity trend-following exploits. Bounded in `[0, 1]`, so it cannot act as a scale proxy. |
> | 7 | `volume_weighted_return_24` | participation-confirmed move | Return per unit of tick volume. Prior: a move on thin participation is more likely to revert, on heavy participation to continue. **See §D — this one carries a pre-committed discount.** |
>
> Ten features, **eleven parameters**. Every feature ships with its causal test per Hard
> Rule 1 and is added to `FEATURE_REGISTRY`, which `tests/test_causality.py` guards against
> the filesystem.

#### §C. `H = 120` cannot support the sign-stability check — and what that forbids

> Measured before registration (`scripts/report_horizon_geometry.py`, merged `ef14b39`):
>
> | | H = 4 | H = 24 | H = 120 |
> |---|---:|---:|---:|
> | decisions/fold | 1,635 | 273 / 272 | **55 / 54** |
> | pooled | 8,175 | 1,364 | **274** |
> | pooled vs K-6 | 54.5x | 9.1x | **1.8x** |
> | smallest fold vs K-6 | 10.90x | 1.81x | **0.36x** |
>
> **At `H = 120` every one of the five folds is below K-6.** Not one marginal fold — all
> five, at 54-55 against a floor of 150. Per-fold results are **not reportable** there and
> the horizon is **pooled-only**.
>
> **This is not a footnote, and here is the specific thing it costs.** The per-fold
> sign-stability check is the diagnostic that caught H-003's reversal in fold 3, and it is
> how "two opposite regimes cancelling" was distinguished from "a small stable effect". A
> pooled number at `H = 120` **cannot make that distinction.** The two are observationally
> identical at that horizon with this geometry, and no amount of care in reading the pooled
> figure recovers the difference.
>
> **Pre-committed, before the run — what a positive result at `H = 120` alone would license:**
>
> - It would license **exactly one thing**: registering a new hypothesis to test the same
>   effect at a geometry that can support per-fold reporting, which means either more data
>   or a different fold count, and which is a new ID and a fresh `N_claims` draw.
> - It would **not** license a directional claim. Not a weak one, not a provisional one, not
>   one with a caveat attached. An effect whose stability cannot be examined has not been
>   shown to be an effect.
> - It would **not** be reported as "H-012 cleared at `H = 120`". It would be reported as
>   "H-012 returned a pooled figure at `H = 120` that no available diagnostic can
>   distinguish from two cancelling regimes."
> - It would **not** satisfy no-condition (iii). A single-horizon positive at the one horizon
>   whose per-fold structure is invisible is the weakest possible evidence in this design,
>   and it is being pre-committed as such now rather than argued about later.
>
> `H = 120` is run anyway. A horizon that cannot support the protocol is a finding to
> register, not a reason to drop it silently — and dropping it after seeing the other two
> would be selection on the result.

#### §D. `volume_weighted_return_24` — the pre-committed discount

> Tick volume is **broker-specific**. It counts price updates on FxPro's feed, not
> contracts traded, and a different broker's tick count for the same hour can differ by an
> order of magnitude. The feature is included because its prior is real; the discount is
> registered now, before the run, so it cannot be softened if this is the feature that fires.
>
> **Pre-committed: if `volume_weighted_return_24` alone carries the effect** — meaning the
> ablation shows it contributing the majority of a clearing result, with the other six
> contributing deltas indistinguishable from zero —
>
> - **that is a finding requiring a second feed before it is believed, not a result.** It
>   would be reported in those words.
> - It does **not** clear no-condition (i) or (ii) for the purposes of this hypothesis. A
>   result resting on a broker-specific quantity is not evidence about gold; it is evidence
>   about FxPro's tick generator until a second feed says otherwise.
> - The required next step would be a **second feed**, not a larger sweep on this one, and
>   that step is registered here so it cannot be replaced with something cheaper later.
> - `RESEARCH.md`'s evidence hierarchy applies: a measurement that cannot be reproduced on
>   an independent instrument is the weakest tier that still counts as a measurement.
>
> This clause exists because the temptation to soften it would be strongest exactly when it
> binds.

#### §E. Attribution — always-long, on anything that clears

> H-007 is the standing lesson: an effect that is long bias is not directional information.
> Any configuration clearing (i) and (ii) is re-run against the always-long control on the
> same decisions, and the long-share of the signal arm is reported beside the base rate.
> **An effect that always-long matches is withdrawn, not caveated.**

#### §F. The ablation is mandatory

> `EVALUATION.md` §7. Each of the seven features is added **individually** to the
> three-feature baseline — seven ablation arms plus the baseline plus the full ten — and the
> delta is reported with its CI.
>
> **Why it is mandatory rather than informative.** Widening the feature set from three to ten
> necessarily takes the combiner from four parameters to eleven. **That is a capacity
> change, and it cannot be avoided** — it is the confound H-011 existed to remove, still
> unremoved and now known to be expensive to remove. Without the ablation, a positive result
> is uninterpretable in exactly the way H-003's was: the effect of *the feature* would be
> inseparable from the effect of *the parameter*.
>
> No ablation arm is a claim. The ablation decomposes one result; it does not generate seven.

#### §G. K-1 at eleven parameters

> The capacity signature added under H-010 keys on the **fitted** parameter count, so moving
> from 4 to 11 fires the guard automatically. The re-measurement is forced, not remembered.
>
> H-010 already measured the null either side of 11: `-0.001754` at 7 parameters and
> `-0.001850` at 10, both silent, both tripping `{label_in_features,
> target_encoding_on_all}`. Eleven sits just past a measured point rather than in unknown
> territory. The re-measurement is still required and its result is reported whatever it is.

#### §H. Standing limitation of the geometry — not of this slice

> **The `2015-09-11` session era never appears in any test window, at any horizon.**
> Measured: in-window composition is `2015-09-11` 12,250 bars, `2017-10-07` 30,945,
> `2022-10-21` 22,200. `first_test_start` is bar 32,697, and the first era ends at 12,250 —
> so **18.7% of the in-window series has never been evaluated out-of-sample, and never can
> be under this split rule.** It is training data only.
>
> Test windows contain two eras, in the same proportion at every horizon: fold 0 entirely
> `2017-10-07`, fold 1 straddling ~60/40, folds 2-4 entirely `2022-10-21`.
>
> **This is a property of the geometry H-001 registered, not of this hypothesis.** It bounds
> every claim this project has made or will make under this split, and it is recorded here
> because this is where a later reader meets it.
>
> **R-001 consequence, found while measuring this.** R-001 is open against the era
> boundaries, which have never been checked against FxPro's own announcements. The exposure
> is narrower than it looks: since only one era boundary falls inside any test window, an
> error in the era derivation would affect **fold 1's composition alone**, not the whole
> test set. Folds 0 and 2-4 are single-era at every horizon and are unaffected by where the
> boundary is drawn. That is a smaller exposure than would have been assumed, and it is
> worth knowing before a result rather than after.

#### §I. Fixed constants, all registered here

> | constant | value | class |
> |---|---|---|
> | horizons | `{4, 24, 120}` | judgement — fixed before the run |
> | BSS floor | `+0.010` | judgement — one fifth of K-3 |
> | BH threshold | `p <= 0.00833` | **forced** — rank 1 at `m = 6`, α = 0.05 |
> | bootstrap block / resamples / seed | 10 / 10,000 / 1337 | **forced** — H-003 §F |
> | `FIRST_TEST_FRACTION`, folds | 0.50, 5 | **forced** — H-001, unchanged |
> | fitting rule | frozen 1,000 iterations | **forced** — H-010 measured the convergent rule unaffordable |
> | feature windows | 120, 480, 4, 480, 480, 24 | judgement — set by the priors in §B |

#### §J. `N_claims` and the critical value, computed before the run

> `N_claims` **5 → 6**: H-003, H-004, H-007, H-009, H-011, H-012.
>
> | rank k | critical `0.05 × k/6` |
> |---|---|
> | **1** | **0.00833** |
> | 2 | 0.01667 |
> | 3 | 0.02500 |
> | 4 | 0.03333 |
> | 5 | 0.04167 |
> | 6 | 0.05000 |
>
> **What registering this costs the family — computed, not assumed.** Available `p` are
> `0.0150` (H-009), `0.0204` (H-003), `0.5041` (H-007). At `m = 6` the step-up finds
> `k = 2`: `0.0204 <= 0.025`. **Both continue to clear §9.** Unlike H-011's registration,
> this one costs the family nothing. Stated because the last two registrations both cost
> something and the pattern should not be assumed either way.
>
> **The step-up route is refused in advance**, as in H-011. With H-009 and H-003 in the
> family the arithmetic would admit a larger `p` for H-012; being carried over the line by a
> claim rejected on magnitude and a claim whose reading is withdrawn is not a correction
> doing its job. **The registered threshold is `p <= 0.00833`.**

#### §K. Pre-committed interpretation

> - **PASS** (all four no-conditions fail to hold): report which of the four cleared and
>   which did not, individually. Register the follow-up as a new hypothesis. No trading
>   claim: this is `EVALUATION.md` §3 probability quality, no cost model, and the §2 ladder
>   is untouched and still halted at rung 2.
> - **FAIL** (all four hold): **the answer is no for this feature set at these horizons.**
>   Record it. Do not widen the set and re-run — that is a new ID and a fresh draw.
> - **AMBIGUOUS:** default REJECT, per §3 of the template.
> - **VOID:** if the capability test fails, or a fit does not converge, or K-1 does not
>   clear at 11 parameters. A non-result is not a negative result.

--- RUN ---

- **Run manifest:** `runs/bd93b544-49c2-42fc-a349-8fa89a7c0cf5.json`
  sha256 `49938ebe120a7a794192f3258370df724c0678f4995889ed5d624037997358ed`
- **run_id:** `bd93b544-49c2-42fc-a349-8fa89a7c0cf5`
- **Executed:** 2026-07-28, commit `9653124`, `git_dirty: false`
- **Registration precedes the code:** registration `64141a7`, implementation `070718f`,
  manifest fix `9653124`. §2 rule 1 satisfied.
- **Data:** snapshot `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6`,
  65,395 in-window bars. Rows: `runs/h012_feature_slice.json`.
- **Determinism:** an earlier execution of the same code produced bit-identical arm
  results; only the manifest step differed. Tier A.
- **Verdict:** **REJECTED. All four no-conditions hold. The answer is no for this feature
  set at these horizons.**

**The primary test**

> | horizon | n | base rate | baseline BSS (4 param) | full BSS (11 param) | ΔBrier | `p` at block 10 |
> |---|---:|---:|---:|---:|---:|---:|
> | 4 | 8,127 | 0.517288 | +0.001851 | **+0.001848** | −0.00000066 | **0.5001** |
> | 24 | 1,356 | 0.536873 | −0.006757 | **−0.004939** | +0.00045190 | **0.3599** |
> | 120 | 272 | 0.555147 | +0.000977 | **+0.003015** | +0.00050325 | **0.4198** |
>
> Block sensitivity, one-sided `p` at blocks 1 / 10 / 25: `0.5024 / 0.5001 / 0.4990` at
> `H = 4`, `0.3846 / 0.3599 / 0.3538` at `H = 24`, `0.4401 / 0.4198 / 0.4021` at `H = 120`.
> **The verdict does not turn on the nuisance parameter at any horizon.**

**The four no-conditions, individually**

> | # | condition | holds? | measured |
> |---|---|---|---|
> | i | magnitude — BSS does not clear `+0.010` | **HOLDS** | best full-set BSS is `+0.003015`, a third of the floor. The best *ablation* arm anywhere is `+log_return_480` at `H = 120`, `BSS +0.007025` — still short, and at the horizon §C makes unreportable per fold. |
> | ii | sign — improvement not distinguishable from zero | **HOLDS** | `p = 0.5001`, `0.3599`, `0.4198`. The threshold is `0.00833`. Not close at any horizon or any block. |
> | iii | horizon — fails at every registered horizon | **HOLDS** | all three. |
> | iv | attribution — nothing surviving always-long | **HOLDS, VACUOUSLY** | **nothing cleared (i) and (ii), so §E's comparison was never reached.** This is recorded as vacuous rather than as a pass: no arm was tested against always-long and survived, because no arm qualified for the test. |
>
> Stating (iv) as vacuous matters. "Attribution held" and "attribution was never tested"
> are different claims, and only the second is true.

**What the always-long numbers show anyway — reported though (iv) was not reached**

> | horizon | base rate | baseline long share | full long share | baseline accuracy | full accuracy |
> |---|---:|---:|---:|---:|---:|
> | 4 | 0.5173 | 0.4991 | 0.5428 | 0.5337 | 0.5321 |
> | 24 | 0.5369 | 0.5575 | 0.6209 | **0.5354** | 0.5398 |
> | 120 | 0.5551 | **0.9265** | 0.7574 | **0.5478** | 0.5625 |
>
> Always-long's accuracy *is* the base rate. **At `H = 24` and `H = 120` the baseline's
> directional accuracy is below it** — `0.5354` against `0.5369`, and `0.5478` against
> `0.5551`. The three-feature model is worse than calling the majority class every time.
>
> At `H = 120` the baseline calls long on **92.65%** of decisions. That is H-007's confound
> in probability space and larger than H-003's 56.2%. Adding seven features moves it to
> 75.74% and buys `+0.0074` of accuracy — a real move, and one that arrives with a
> `p` of `0.4198`.

**Per fold — and the thing `H = 120` cannot show**

> | horizon | per-fold BSS, full set |
> |---|---|
> | 4 | `+0.041436, +0.004709, −0.009625, −0.028047, −0.007495` |
> | 24 | `+0.048762, +0.012931, −0.042581, −0.042214, −0.014213` |
> | 120 | *(not reportable — every fold below K-6)* |
>
> **At both reportable horizons the sign flips and the decline is monotone through fold 3.**
> Positive in folds 0 and 1, negative in folds 2, 3 and 4 — the same shape H-003 showed and
> H-007 explained. The pooled figure is two opposing regimes cancelling, not a small stable
> effect, and this is visible only because per-fold reporting exists at these horizons.
>
> **At `H = 120` it is invisible, exactly as §C pre-committed.** Its pooled `+0.003015`
> could be either shape and no available diagnostic distinguishes them. §C's clause is
> therefore not hypothetical: had `H = 120` cleared, it would have cleared as the one
> horizon whose structure cannot be examined.

**K-1 re-measurement at eleven parameters — the guard fired and the gate cleared**

> | horizon | mode | p | mean BSS | max | CI upper | K-1 |
> |---|---|---:|---:|---:|---:|---|
> | 4 | `none` | 11 | −0.000477 | +0.000176 | −0.000349 | **PASS** |
> | 24 | `none` | 11 | −0.001231 | +0.000921 | −0.000817 | **PASS** |
> | 120 | `none` | 11 | −0.002920 | +0.002537 | −0.001582 | **PASS** |
> | 4 / 24 / 120 | `label_in_features` | 12 | +0.999984 / +0.999984 / +0.999983 | | | **trips, as required** |
>
> The capability test passes at every horizon: the combiner detects a planted label. The
> null at 11 parameters sits between H-010's measurements at 7 (`−0.001754`) and 10
> (`−0.001850`) for the shorter horizons and below both at `H = 120`, where n is smallest.

**Convergence — and a contrast with H-010 worth recording**

> Worst gradient infinity-norm across folds, at the registered frozen 1,000 iterations:
>
> | | 4-parameter baseline | 11-parameter full set |
> |---|---:|---:|
> | H = 4 | `1.19e-16` | `8.53e-07` |
> | H = 24 | `3.29e-16` | `1.60e-06` |
> | H = 120 | `3.41e-17` | `7.49e-07` |
>
> **Eleven parameters of real features are essentially converged at a thousand steps.** Two
> of three are inside H-011's `1e-6` tolerance and the third misses it by 60%.
>
> Contrast H-010: at twenty parameters of *polynomial* design the same budget left the
> gradient at `2.4e-04`, and at thirty-five it stalled at `0.15`. **The optimiser problem
> H-010 hit was a property of the polynomial basis, not of parameter count.** A design
> matrix of genuinely different measurements is well-conditioned where a basis expansion of
> three columns is not. That is a useful thing to know and neither hypothesis predicted it.

**§9 — the family after this run**

> `N_claims = 6`. Available `p`: `0.0150` (H-009), `0.0204` (H-003), `0.4198` (H-012, best
> across horizons), `0.5041` (H-007). Critical values `0.00833, 0.01667, 0.025, 0.0333,
> 0.0417, 0.05`. Step-up finds `k = 2`: `0.0204 <= 0.025`. **H-009 and H-003 continue to
> clear §9 and H-012 does not**, exactly as §J computed before the run.

**Notes**

> - The `n` differs slightly from the geometry report (8,127 / 1,356 / 272 against
>   8,175 / 1,364 / 274). Eligibility is computed once from the **ten**-feature design so
>   every arm decides on identical rows; the 480-bar lookbacks disqualify a few more bars
>   near gaps. The baseline's `H = 24` BSS is `−0.006757` here against H-001's `−0.006766`
>   on 1,364 rows — the same quantity on 8 fewer decisions, not a discrepancy.
> - `reversal_4` is exactly `−log_return_4` and a linear combiner cannot distinguish them.
>   Its arm is therefore a test of the 4-bar return, and it is the **worst** ablation arm at
>   `H = 4` (`BSS +0.000838`, `p = 0.9296`). The prior was stated; it did not survive.
> - §D's clause was not triggered: `volume_weighted_return_24` is the weakest arm at
>   `H = 4` (`p = 0.9984`) and near-weakest at `H = 24`. No second feed is required, because
>   there is nothing to reproduce.
> - No cost model, no trade, no baseline ladder, no holdout. `EVALUATION.md` §2's ladder
>   remains halted at rung 2.
> - Any new idea in this block becomes a **new hypothesis**, not an amendment to this one.

<!-- H-013 onward -->
