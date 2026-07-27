# HYPOTHESES.md — Pre-Registration Registry

**Append-only. Nothing is ever deleted or edited after its run.**
**Version:** 1.0

---

## 0. Running Counters

> Updated on every merge. These three numbers gate the validity of every claim the project
> makes.

```
Registered (registry completeness) ... 6
  ├─ Accepted ....................... 0
  ├─ Rejected ....................... 0
  ├─ Standing ....................... 1
  └─ In flight ...................... 5

N_claims (multiple-testing denom.) ... N = 2
  ├─ gates  (not counted) ........... 4   H-001, H-002, H-005, H-006
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

**Guardrail — what this must not become**

> `window_start` may be moved **later** without a new hypothesis; a shorter window is
> conservative and cannot manufacture an edge. Moving it **earlier requires a new
> hypothesis ID**, and moving it after seeing a result that the later start killed is
> hypothesis laundering under `RESEARCH.md` §5.2 whatever the accompanying justification.
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
- **Pending for `STANDING`:** conditions (i)–(iv) become build-enforced when the loader and
  manifest writer exist. Until then the date is frozen but nothing asserts it, because
  there is no code yet that could violate it.

<!-- H-007 onward -->
