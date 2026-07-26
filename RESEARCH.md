# RESEARCH.md — Research Constitution

**Status:** Locked. Changes require a hypothesis in `HYPOTHESES.md` and two-party sign-off.
**Version:** 1.0

---

## 0. The Null Hypothesis

> **Default position: this system has no edge.**

Every result is presumed to be noise, leakage, or overfitting until it survives the
protocol in `EVALUATION.md`. The burden of proof is on the feature, the agent, or the
architecture — never on the skeptic.

This is not pessimism. It is the only stance under which a positive result means anything.

---

## 1. What We Are Building

A **quant research platform** that:

- extracts market state deterministically and reproducibly,
- generates directional hypotheses with calibrated probabilities,
- subjects every hypothesis to adversarial testing before it can influence anything,
- and logs every decision with full provenance so it can be audited a year later.

## 2. What We Are Explicitly Not Building

- An autonomous system that trades unsupervised capital.
- A predictor. We produce **calibrated probabilities**, not forecasts.
- A system whose edge derives from LLM "market intuition". No such thing exists.
- A backtest-optimised strategy. Backtests are used to *falsify*, not to *tune*.

---

## 3. Division of Labour: Deterministic vs. Language Model

This split is the architectural spine of the project. It is not negotiable without a
hypothesis.

| Concern | Owner | Why |
|---|---|---|
| Price/volume features, ATR, sessions | Deterministic Python | Arithmetic. Testable. Reproducible. |
| Structure (BOS, swing points, FVG, order blocks) | Deterministic Python | Rule-definable. If it can't be defined, it can't be tested. |
| Liquidity pools, equal highs/lows | Deterministic Python | Geometric. |
| Macro correlations (DXY, yields, VIX, oil) | Deterministic Python | Statistical. |
| Event calendar, embargo windows | Deterministic Python | Lookup table. |
| Contradiction detection across agents | LLM | Language task. Genuine fit. |
| Requesting additional evidence | LLM | Language task. |
| Human-readable decision narrative | LLM | Language task. Its best use. |
| **Final directional decision** | **Under test** | See §6. |

**Rule:** if a step can be written as a testable function, it must be. An LLM is
permitted only where the task is genuinely linguistic.

---

## 4. Hierarchy of Evidence

Ranked. Lower tiers cannot override higher tiers.

**Tier 1 — Admissible as proof**
- Out-of-sample performance on the sealed holdout, under the full cost model, beating
  the baseline ladder with pre-registered metrics.

**Tier 2 — Admissible as support**
- Walk-forward results with purge and embargo applied.
- Ablation deltas with confidence intervals.
- Calibration curves over ≥150 decisions.

**Tier 3 — Admissible as a hypothesis generator only**
- In-sample results.
- Visual chart inspection.
- Analogy to published literature.
- Anything produced before the LLM knowledge-cutoff date (see `DATA_CONTRACT.md` §5).

**Tier 4 — Inadmissible**
- "It makes sense."
- "This is how professional traders do it."
- An LLM's stated confidence, absent calibration data.
- A backtest whose parameters were chosen after seeing that backtest.
- Any result that cannot be reproduced from a run manifest.

---

## 5. Prohibited Reasoning Patterns

Each of these has a name because each of these will be attempted.

1. **Post-hoc narration.** Explaining why a losing trade lost, then adding a filter to
   exclude it. This is curve-fitting with extra steps.
2. **Hypothesis laundering.** Running an experiment, seeing the result, then writing the
   hypothesis. Prevented structurally — see `HYPOTHESES.md` §2.
3. **Metric shopping.** Reporting the metric that looks best. The metric is named in the
   hypothesis before the run.
4. **Baseline omission.** Reporting absolute performance without the random-entry
   baseline beside it. A result without its baseline is not a result.
5. **Sample-size silence.** Quoting a percentage without n and a confidence interval.
6. **Complexity as evidence.** A more sophisticated architecture is not more likely to be
   correct. Every added layer must earn its place through ablation.
7. **Selective memory.** Deleting failed hypotheses. They stay in the registry forever —
   they are the denominator for multiple-testing correction.

---

## 6. Standing Challenges

These are permanent open questions. They are re-tested every quarter, and the project's
answer to them may change.

- **SC-1: Does the LLM belong in the decision path at all?**
  Contenders: LLM synthesis / equal-weight vote / logistic regression stacker /
  gradient-boosted stacker. If a free, deterministic, fully-interpretable method matches
  or beats the LLM, the LLM is removed from the decision path and retained only for
  narrative generation. No sunk-cost defence is admissible.

- **SC-2: Does agent multiplicity add information, or just correlated noise?**
  Measured by effective independent agent count `N_eff` (`EVALUATION.md` §6). If
  `N_eff < 2` across a seven-agent panel, the panel is theatre and should be collapsed.

- **SC-3: Does adaptive weighting beat equal weighting?**
  The forecast-combination literature says usually not. Assumed **not** until proven
  otherwise on out-of-sample data. Weights are frozen at equal for a minimum of 12 months.

- **SC-4: Does any of this beat buy-and-hold on a risk-adjusted basis, after costs?**
  Asked honestly, every quarter.

---

## 7. Decision Rights

| Action | Requires |
|---|---|
| Add/modify a feature | Hypothesis + causal test pass |
| Add/modify an agent | Hypothesis + ablation showing positive delta |
| Change a prompt | Hypothesis. Prompts are code. |
| Change agent weights | Hypothesis + n ≥ 100 per agent + shrinkage rule |
| Touch the sealed holdout | Explicit sign-off. Budget-tracked. See `EVALUATION.md` §8. |
| Relax a kill criterion | Not permitted. Kill criteria are immutable for the project's life. |
| Change a threshold, metric, baseline, or label definition | Hypothesis required |
| Clarify, define, or restate procedure without changing what counts as a result | No hypothesis; note the rationale in the commit |

The test is effect, not location. If the edit could change whether a past or future run
counts as a pass, it needs a hypothesis. `EVALUATION.md` §1 remains immutable regardless.

---

## 8. Failure Is a Valid Outcome

If the protocol concludes that the system has no edge, the correct action is to publish
that result internally, archive the repository, and stop. A well-executed negative result
is a successful project. Time saved is the return.

The failure mode this document exists to prevent is not losing money. It is spending two
years unable to answer the question *"do we actually have an edge?"*
