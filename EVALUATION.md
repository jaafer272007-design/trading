# EVALUATION.md — Measurement Protocol

**Status:** §1 (Kill Criteria) is immutable. Everything else requires a hypothesis to change.
**Version:** 1.0

---

## 1. Kill Criteria — IMMUTABLE

Written before any code. Locked by commit hash. **Cannot be relaxed, reinterpreted, or
"contextualised" at any point in the project's life.**

| ID | Condition | Action |
|---|---|---|
| K-1 | Shuffled-labels test shows measured edge outside the null distribution | **Halt immediately.** Leakage or bug. Nothing downstream is valid. |
| K-2 | Any feature fails the causal test | **Halt.** Fix before any further run. |
| K-3 | Brier Skill Score ≤ 0.05 on sealed holdout | Terminate the configuration. |
| K-4 | Fails to beat random-entry baseline at p < 0.05 | Terminate. The edge was risk management, not signal. |
| K-5 | Edge disappears when all costs are doubled | Terminate. Edge is within the noise of execution. |
| K-6 | Fewer than 150 closed decisions in the evaluation window | **Not a negative result — no result.** Do not conclude anything. |
| K-7 | Deflated Sharpe Ratio ≤ 0 after correcting for trials attempted | Terminate. |
| K-8 | Live/paper calibration diverges from backtest calibration by > 0.10 BSS | Halt live operation. Investigate before resuming. |

> A configuration that trips a kill criterion is recorded as **rejected** in
> `HYPOTHESES.md` and is not silently re-run with tweaks. Re-testing requires a new
> hypothesis ID and counts against the multiple-testing budget.

---

## 2. Baseline Ladder

The system must beat these **in order**. Failing rung *n* makes rungs *n+1* onward
meaningless — do not report them.

| # | Baseline | What it isolates |
|---|---|---|
| 0 | **Shuffled labels** | Pipeline integrity. Must show **zero** edge. |
| 1 | **Random entry, identical risk management** | Is the edge in the signal, or in the stop/target geometry? |
| 2 | **Always-long** | Gold has a secular uptrend. Any long-biased system looks clever. |
| 3 | **Buy-and-hold, risk-parity sized** | Risk-adjusted honesty. |
| 4 | **Single moving-average crossover** | Can three lines of code match the whole platform? |
| 5 | **One agent, no debate, no judge** | Value of the multi-agent architecture itself. |
| 6 | **Equal-weight vote over agents, no LLM** | Value of the LLM in the decision path (SC-1). |
| 7 | **Logistic regression stacker on agent outputs** | Value of the LLM vs. a free, interpretable alternative. |

**Rung 1 is the one that kills most retail systems.** It runs on every evaluation, always,
reported side-by-side. Never report system performance without it.

---

## 3. Probability Quality (Primary Metrics)

The system outputs probabilities, so it is scored as a probabilistic forecaster first and
a trading strategy second.

### 3.1 Brier Score
```
BS = (1/N) · Σ (f_i − o_i)²
```
`f_i` = forecast probability, `o_i` ∈ {0,1} = outcome. Lower is better.

### 3.2 Brier Skill Score — the headline number
```
BSS = 1 − (BS_model / BS_reference)
```
`BS_reference` = base rate (climatology) over the same window.

- `BSS ≤ 0` → worse than always predicting the base rate.
- `BSS ≤ 0.05` → **K-3 trips.**
- Report with bootstrap 95% CI. A BSS of 0.08 [−0.04, 0.19] is not a result.

### 3.3 Reliability Diagram
Bin forecasts into deciles; plot mean forecast vs. observed frequency. Report:
- **Calibration error (ECE):** weighted mean |forecast − observed| across bins.
- **Overconfidence ratio:** mean forecast ÷ mean outcome in the top two deciles.

> Expect systematic overconfidence from LLM-derived probabilities. A stated 75% commonly
> realises near 55%. Debate layers **amplify** this rather than correcting it — the panel
> converges on a shared narrative and reads that convergence as evidence.

### 3.4 Decomposition
```
BS = Reliability − Resolution + Uncertainty
```
Track all three. High resolution with poor reliability is fixable by recalibration
(Platt/isotonic). Low resolution means there is no signal, and no amount of calibration
will create one.

---

## 4. Trading Metrics (Secondary)

Reported only after §3 passes. Always with bootstrap CIs over resampled trade sequences.

- CAGR, volatility, Sharpe, Sortino
- Max drawdown, drawdown duration, Ulcer index
- Hit rate, profit factor, expectancy per trade
- Turnover and total cost drag as % of gross return
- **Regime-conditional breakdown** — a system that only works in one regime is a bet on
  that regime, not a system.

### 4.1 Deflated Sharpe Ratio
Mandatory. With `N` configurations tried, the best observed Sharpe is inflated by
selection. DSR (Bailey & López de Prado) adjusts for:
- number of independent trials `N` (taken from `HYPOTHESES.md` count),
- non-normality (skew, kurtosis) of returns,
- sample length.

`DSR ≤ 0` trips **K-7**.

---

## 5. Leakage Controls

### 5.1 Shuffled-Labels Test (runs first, always)
Randomly permute the mapping between market-state snapshots and their outcomes, then run
the full pipeline.

- Run over **≥ 30 seeds** to build a null distribution.
- Pass condition: measured edge falls **inside** the null distribution's 95% interval.
- Any edge on shuffled labels means leakage or a bug. **K-1.**

### 5.2 Purge and Embargo
With label horizon `H`:
- **Purge:** drop training samples whose label window overlaps the test window.
- **Embargo:** additionally drop a buffer of length `H` immediately after the test window.

Without both, adjacent overlapping labels leak test information into training.

### 5.3 Causal Feature Test
Every feature computed at bar `T` must use only data timestamped `≤ T`. Enforced by an
automated test that recomputes each feature on truncated data and asserts equality.
Failure trips **K-2**. Specification lives in `DATA_CONTRACT.md`.

### 5.4 Knowledge-Cutoff Contamination
Any evaluation window predating the pinned model's training cutoff is **Tier 3 evidence
only** (`RESEARCH.md` §4) unless run under the anonymisation protocol in
`DATA_CONTRACT.md` §5.

---

## 6. Evidence Independence — `N_eff`

Prevents false confidence from agents that agree because they read the same information.

**Step 1 — Feature overlap.** Jaccard similarity between the sets of features each pair of
agents cited.

**Step 2 — Signal correlation.** Correlation matrix `C` of agents' historical *directional
calls* (not their stated confidence).

**Step 3 — Effective agent count.** Eigenvalues `λ₁…λ_k` of `C`, normalised so `Σλ = k`:

```
N_eff = (Σ λᵢ)² / Σ (λᵢ²)
```

- Identical agents → `N_eff = 1`
- Fully independent agents → `N_eff = k`
- If PC1 explains > 80% of variance, the panel is effectively one agent.

**Step 4 — Confidence discount.** Proposed rule (itself subject to a hypothesis before
adoption):
```
p_adjusted = 0.5 + (p_raw − 0.5) · √(N_eff / k)
```

> Feature-level overlap **understates** dependence. DXY and 10y yields are strongly
> correlated; two agents citing "different" features may be reading one signal. Compute
> correlation among the underlying features as well.

---

## 7. Ablation Protocol

For each component: remove it, re-run the full evaluation, report the delta with CIs.

- Any component whose removal produces a delta indistinguishable from zero is **deleted**,
  not kept "just in case". Token cost without measured benefit is negative value.
- **Devil's Advocate special case:** log every trade it vetoed and track the counterfactual
  outcome. This is the only way to distinguish protection from opportunity cost. Report
  vetoed-trade expectancy alongside taken-trade expectancy.

---

## 8. Holdout Policy

- The final holdout is **sealed**. It lives in a separate location and is not readable by
  the development pipeline.
- **Budget: 3 openings for the life of the project.** Each opening is logged in
  `HYPOTHESES.md` with a date and a reason.
- Openings remaining is displayed in every evaluation report header.
- After the third opening, the holdout is exhausted and no further claim of out-of-sample
  validity can be made from it.

---

## 9. Multiple-Testing Correction

`HYPOTHESES.md` maintains the count `N` of all hypotheses tested — including rejected ones.
This count is the project's most important number.

- Apply **Benjamini–Hochberg FDR** across all hypotheses at a given decision point.
- Feed `N` into the Deflated Sharpe Ratio.
- With 74 hypotheses at α = 0.05, roughly 4 will pass by chance alone. Correct, or the
  registry becomes a machine for manufacturing false positives.

---

## 10. Cost Model

Backtests use the pessimistic model. Optimistic assumptions are not permitted.

| Component | Model |
|---|---|
| Spread | Session-dependent + event multiplier. Widens 3–10× around scheduled news and at the weekly open. Never a constant. |
| Slippage | Function of ATR and order size, not a fixed pip value. |
| Stop execution | Gap-through modelling. Stops do **not** fill at the stop price. |
| Commission | Per-lot, both sides. |
| Swap | Applied to all positions held past rollover. |
| Latency | Configurable delay between signal and fill; default 250 ms, stress-tested at 500 ms+. |

**Doubling test:** double every cost above and re-run. Edge disappearing trips **K-5**.

---

## 11. Adversarial / Robustness Harness

Deterministic perturbation sweep — **no LLM involved**. Reports a *distribution* of
outcomes, never a point estimate.

| Perturbation | Range |
|---|---|
| Spread multiplier | 1× – 5× |
| Execution latency | 0 – 1000 ms |
| Data dropout | 0 – 15% of bars randomly removed |
| Feature jitter | ±1 σ noise added to each continuous feature |
| News timing shift | ±30 min |
| Start-date shift | ±20 bars (tests calendar-alignment luck) |
| Parameter jitter | ±20% on every tunable constant |

**Structural stress — more informative than any of the above:**
- **Regime-shift test:** fit/develop pre-2022, evaluate post-2022. The rate-hiking cycle
  changed gold's behaviour structurally. This is far harsher than spread ×3, and far more
  representative of what live deployment actually faces.

Pass condition: median performance stays above the baseline ladder and the 5th percentile
remains non-catastrophic.

---

## 12. Reporting Template

Every evaluation report must contain, in this order:

1. Run manifest hash, holdout openings remaining, cumulative hypothesis count `N`
2. Shuffled-labels result (pass/fail + null distribution plot)
3. Causal test result
4. Baseline ladder table — all rungs, system alongside each
5. BSS with bootstrap CI, reliability diagram, ECE
6. `N_eff` and PC1 variance share
7. Trading metrics with CIs, regime-conditional breakdown
8. Deflated Sharpe with `N` used
9. Ablation table
10. Robustness distribution (median, 5th, 95th percentile)
11. **Sample size, stated plainly, at the top of every percentage in the document**

A report missing any section is not a report.
