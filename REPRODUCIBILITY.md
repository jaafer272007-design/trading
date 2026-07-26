# REPRODUCIBILITY.md — Determinism and Provenance

**Target: any result produced today can be reproduced bit-for-bit in twelve months.**
**Version:** 1.0

---

## 1. Determinism Tiers

| Tier | Components | Guarantee |
|---|---|---|
| **A — Bit-exact** | Data layer, features, backtest engine, metrics, stackers | Identical inputs → identical outputs, always. Enforced by test. |
| **B — Statistically stable** | LLM at temperature 0, pinned model version | Not bit-exact. Variance must be measured and reported. |
| **C — Non-reproducible** | Any unpinned model, any live API without response caching | **Prohibited in the evaluation path.** |

> Tier B is the reason `HYPOTHESES.md` H-004 exists. If a deterministic stacker matches the
> LLM, the system moves entirely to Tier A. That is a substantial engineering win
> independent of accuracy.

---

## 2. Model Pinning

**A model version change silently changes your system and invalidates every prior
backtest.** This will happen at least once during the project.

```yaml
llm:
  provider: anthropic
  model_id: <exact-versioned-string>     # never a floating alias
  temperature: 0
  top_p: 1
  max_tokens: <fixed>
  system_prompt_sha256: <hash>
  user_prompt_template_sha256: <hash>
  pinned_on: YYYY-MM-DD
```

Rules:
- **Never use a floating model alias** in the evaluation path.
- Prompts are code: versioned, hashed, reviewed, and changed only via a hypothesis.
- On model upgrade: re-run the **full baseline ladder** before comparing anything to
  historical results. Cross-version comparison without re-baselining is invalid.
- Store the full request and response for every decision. Storage is cheap; an
  unreproducible year is not.

### Measuring Tier B variance
Run the identical decision set 10 times at temperature 0. Report disagreement rate and
confidence standard deviation. If disagreement exceeds 5%, the LLM path is too unstable for
the decision role — record it as evidence for SC-1.

---

## 3. Seeds

```yaml
seeds:
  numpy: 42
  python_random: 42
  torch: 42            # if used
  bootstrap: 1337
  shuffled_labels: [0..29]   # 30 seeds, enumerated not generated
  robustness_sweep: 7
```

- Every stochastic process draws from a named, logged seed.
- Results are reported across a **seed sweep**, never a single seed. A finding that holds
  on one seed and not others is a finding about the seed.

---

## 4. Environment Lock

- `uv.lock` or `poetry.lock` committed. Exact transitive pins.
- Python version pinned. Container image digest-pinned, not tag-pinned.
- OS-level BLAS threading fixed (`OMP_NUM_THREADS=1`) — parallel float reduction ordering
  changes results in the last bits and will silently break bit-exactness tests.
- Hardware class recorded in the manifest.

---

## 5. Run Manifest

Emitted for every run. Without it, the result does not exist.

```yaml
run_id: <uuid>
timestamp_utc: <iso8601>
git_commit: <hash>
git_dirty: false              # a dirty tree voids the run
hypothesis_id: H-0XX          # required — no unregistered runs
data_snapshot_sha256: <hash>
data_window: {start: ..., end: ...}
evaluation_mode: walk_forward | holdout
holdout_openings_remaining: <n>
cumulative_hypothesis_count_N: <n>
feature_set_version: <hash>
llm: {model_id: ..., temperature: 0, prompt_sha256: ...}
seeds: {...}
cost_model_version: <hash>
env_lock_sha256: <hash>
anonymisation_protocol: A | B | none
runtime_seconds: <n>
```

`git_dirty: true` voids the run. No exceptions — an uncommitted change is an unrecorded
change.

---

## 6. CI Pipeline

Structured in two tiers so that the cheap, decisive tests gate everything.

### Tier 1 — every commit, deterministic only, target < 5 minutes

```
1. lint + type check
2. unit tests (features, engine, metrics)
3. DATA CONTRACT: causal feature test          → fail = K-2 halt
4. LEAKAGE: purge/embargo integrity check
5. SHUFFLED LABELS (deterministic path, 30 seeds) → fail = K-1 halt
6. RANDOM-ENTRY BASELINE regression
7. bit-exactness: rerun fixed fixture, assert identical output
```

Steps 3 and 5 are **hard gates**. On failure the pipeline stops — the backtest is not
permitted to run, because its output would be meaningless.

> **Practical note:** run the shuffled-labels gate on the deterministic path
> (features → stacker), not the full LLM path. It needs 30 seeds and must stay fast enough
> that nobody is tempted to skip it. The LLM path gets the same test nightly.

### Tier 2 — nightly / pre-merge, expensive

```
8.  full LLM path, shuffled labels, 30 seeds
9.  full baseline ladder (rungs 0–7)
10. walk-forward with purge + embargo
11. calibration + N_eff report
12. ablation sweep
13. robustness / adversarial sweep
14. Tier B variance measurement (10× repeat)
```

### Never in CI
The sealed holdout. It is opened manually, with sign-off, three times in the project's
life.

### K-1 sensitivity is a property of the combiner

K-1 sensitivity is a property of the combiner, not of the gate. `train_test_overlap` is
undetectable at four parameters and becomes detectable as capacity grows. Any change to
the combiner — different estimator, added parameters, changed regularisation — requires
re-running the full leak-fixture suite and recording which modes trip. A combiner change
without a recorded sensitivity re-measurement invalidates every subsequent K-1 pass.

**Enforcement.** `src/evaluation/sensitivity.py` holds the recorded baseline alongside a
semantic fingerprint of the combiner module. `tests/evaluation/test_sensitivity.py` fails
the build when the fingerprint moves without a matching re-measurement — the same pattern
as the feature-registry guard in `tests/test_causality.py`. The fingerprint is taken over
the parsed AST with docstrings stripped, so comments and formatting do not trip it but
any change to logic, hyperparameter defaults, or structure does.

**Recorded baseline** — 30 seeds, 834 pooled decisions, 30,000 synthetic bars, combiner
at **4 parameters** (3 features + intercept):

| Leak mode | mean BSS | Gate |
|---|---:|---|
| `none` | −0.001390 | pass |
| `label_in_features` | +0.999984 | **trips K-1** |
| `target_encoding_on_all` | +0.239781 | **trips K-1** |
| `train_test_overlap` | −0.000901 | silent — below capacity |
| `scaler_fit_on_all` | −0.001390 | silent — leaks no label information |

Two of five modes trip. The two silent modes are silent for different reasons, and only
one of them is a capacity limit: `scaler_fit_on_all` carries no label information at all
and would stay silent at any capacity, whereas `train_test_overlap` is a real leak that a
higher-capacity estimator would catch.

---

## 7. Decision Log Schema

Every decision — backtest, paper, or live — is stored identically. This is the Evidence
Graph as data.

```json
{
  "decision_id": "uuid",
  "run_id": "uuid",
  "bar_timestamp_utc": "iso8601",
  "snapshot_sha256": "hash",
  "features": {"<name>": {"value": 0.0, "version": 1, "computed_at": "iso8601"}},
  "agents": [
    {
      "agent_id": "liquidity_v3",
      "prompt_sha256": "hash",
      "direction": "long|short|no_signal",
      "confidence_raw": 0.71,
      "evidence_refs": ["equal_highs_level", "liquidity_sweep_high"],
      "raw_response": "..."
    }
  ],
  "evidence_graph": { "nodes": [], "edges": [] },
  "n_eff": 2.3,
  "pc1_variance_share": 0.62,
  "confidence_adjusted": 0.58,
  "devils_advocate": {"verdict": "veto|pass", "grounds": "...", "counterfactual_tracked": true},
  "final_decision": "long|short|flat",
  "decision_method": "llm|equal_vote|logistic|xgboost",
  "costs_applied": {"spread": 0.0, "slippage": 0.0, "latency_ms": 250},
  "outcome": {"h1": null, "h4": null, "h24": null}
}
```

Notes:
- `evidence_refs` must name **computed features**, not free text. An agent citing something
  absent from the feature registry is a validation error, not a warning.
- Vetoed trades are logged with `final_decision: flat` and their counterfactual outcome
  tracked — required by `EVALUATION.md` §7.
- Outcomes are filled asynchronously as horizons close.

---

## 8. Archival

- Decision logs, run manifests, and data snapshots retained for the project's full life.
- Monthly cold-storage export.
- **Restore drill quarterly:** pick a random result from ≥ 3 months prior and reproduce it
  from the manifest alone. A reproducibility policy that is never exercised is not a
  policy.
