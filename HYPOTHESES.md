# HYPOTHESES.md — Pre-Registration Registry

**Append-only. Nothing is ever deleted or edited after its run.**
**Version:** 1.0

---

## 0. Running Counters

> Updated on every merge. These three numbers gate the validity of every claim the project
> makes.

```
Total hypotheses registered ......... N = 4
  ├─ Accepted ....................... 0
  ├─ Rejected ....................... 0
  └─ In flight ...................... 4

Holdout openings used ............... 0 / 3
FDR correction level ................ α = 0.05, Benjamini–Hochberg
```

In flight = status REGISTERED or RUNNING.

**`N` is the denominator for every significance claim in this project.** It is passed to
the Deflated Sharpe Ratio and the BH-FDR procedure. Rejected hypotheses count. Abandoned
hypotheses count. This is the entire reason the registry exists.

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
- **Status:** REGISTERED

**Claim**
> With labels randomly permuted, the full pipeline will show measured edge inside the 95%
> interval of the null distribution across ≥ 30 seeds.

**Primary metric & threshold**
> Measured BSS on shuffled labels within null 95% CI. Any edge = FAIL.

**Pre-committed interpretation**
> - PASS: proceed to H-002.
> - FAIL: **K-1 halt.** Full leakage audit. No other work proceeds.

---

### H-002 — Temporal causality of all features

- **Registered:** 2026-07-26 14:32 UTC
- **Status:** REGISTERED

**Claim**
> Every feature recomputed on data truncated at bar `T` will be bit-identical to its value
> in the full-history computation at bar `T`.

**Primary metric & threshold**
> 100% of features pass. Any failure = FAIL.

**Pre-committed interpretation**
> - FAIL: **K-2 halt.** The failing feature is disabled until fixed.

---

### H-003 — Signal beats random entry

- **Registered:** 2026-07-26 14:32 UTC
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
