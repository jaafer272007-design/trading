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

---

## 9. Provenance of Reported Numbers

**Every quantitative claim in a report carries its provenance. A number without one is not
reportable.**

| Tag | Meaning |
|---|---|
| `[MEASURED]` | Counted or computed directly from the data being described. No modelling step between the data and the number. |
| `[ESTIMATE]` | Derived from measured quantities under a stated assumption. **The assumption is named at the point of use**, not left to the reader. An extrapolation, a rate, a projection, and an interpolation are all estimates. |
| `[FIXTURE]` | Produced by synthetic or test data. Describes the instrument, never the world. |

### Why this exists

Two numbers in this project were reported as measured and were not:

| Number | Claimed | Actually | Error |
|---|---|---|---|
| **4,579** "total independent decisions" | measured | median-bars-per-week × 52 × years | 63% above the measured ceiling of 2,806 |
| **2,600** daily-break observations, "~5× the weekly open" | measured | a test fixture: 520 weeks × 5 days | live figure is 1,055, about 2× |

Neither was a calculation error. Both were fluent, plausible, and load-bearing in an
argument, and both survived review because nothing in the sentence marked them as anything
other than counts. That is the failure mode this rule addresses: not arithmetic, but a
number arriving without the one piece of metadata that would have made it checkable.

### Scope — the part that matters

The instrument already labels its own output. **Both errors appeared in prose**: a report
paragraph and a pull-request body. So the rule applies wherever a number is asserted:

- run reports and evaluation writeups
- pull-request titles and bodies
- commit messages
- hypothesis entries in `HYPOTHESES.md`
- code comments and docstrings that quote a figure
- any message to a human that carries a number

Tool output that already labels itself satisfies this by construction. Quoting that output
into prose does **not** inherit the label — restate it.

### Enforcement

This is a reporting discipline, not a kill criterion, and carries no K-code
(`CLAUDE.md` Hard Rule 4). It cannot be usefully automated: the failure is a true number
described wrongly, which no linter can see. It is enforced at review, and the correct
response to an unlabelled number is to ask where it came from before reading further.

A number whose provenance cannot be established after the fact is not downgraded to
`[ESTIMATE]`. It is **withdrawn**.

---

## 10. Gates Must Pass For A Statable Reason

**A gate that passes for a reason nobody can state is not a passing gate.** When a
threshold catches something, the person who set it must be able to say *why* it caught it.
If the answer is "it happened to land on the right side of the line", the gate has not
detected anything — it has produced a green tick that will not survive the next dataset.

This is §9's sibling. §9 is about a number arriving without provenance; this is about a
**verdict** arriving without a mechanism. Both are cases of something load-bearing being
accepted because it looked right.

### The instance

`data/invariants.py` checks that payrolls activity peaks in the bar containing the 08:30
New York release. It has a floor on how dominant that peak must be, `MIN_PEAK_SHARE`,
whose job is to stop a mode computed from noise being read as agreement.

It was first set at **0.30**. Against the four deliberately-broken conversions the suite
runs, that produced:

| mutation | peak hour | share | caught? |
|---|---|---|---|
| correct | 08:00 ✓ | 0.376 | — |
| shifted ±1h | 07:00 / 09:00 ✗ | 0.384 | yes, by the **mode** |
| fixed offset | 08:00 ✓ | 0.312 | no |
| US transition dates | 08:00 ✓ | **0.280** | **yes, by the threshold** |

The last row is the problem. That mutation puts the peak in the **correct hour** — it is
wrong only in the four weeks a year the US and EU calendars disagree, and payrolls rarely
lands in one. The check's actual mechanism, "the busiest hour is the release hour", did
not detect it. The threshold fired because a share that should have been irrelevant
happened to come in 0.02 under an arbitrary line.

Keeping 0.30 was tempting: it made the coverage table look better and cost nothing. It
would have recorded a detection nobody could explain, and any change to the sample —
another year of data, a different symbol — would have flipped it back with no warning and
no way to tell what had changed.

The floor was lowered to **0.25**, where it does only its stated job. That mutation is
caught decisively elsewhere, by the weekly close, at 66 of 576 weeks.

### The rule

When a gate fires:

1. **Name the mechanism.** Which property of the data made it fire? If the answer is the
   threshold rather than the property, that is a coincidence, not a detection.
2. **Do not keep a threshold for a catch it was not designed to make.** Tightening a bound
   until it catches one more case is fitting the gate to the test set, and it is the same
   error as choosing a metric after seeing which one wins (`RESEARCH.md` §5.3).
3. **Record the misses.** A coverage table with only hits in it cannot be checked. Blind
   spots are asserted as tests here — see `tests/data/test_invariants.py::
   test_the_measured_coverage_matrix_still_holds`, whose `False` cells are the point.
4. **A gate that has never fired is indistinguishable from one that cannot.** Every guard
   in this project ships with a demonstration that it rejects something, and where a guard
   turns out to reject nothing, that is recorded rather than quietly tolerated —
   `assert_release_hour_is_covered` caught none of the four mutations, so it was renamed
   to what it actually is.

### Enforcement

Review, like §9. This is not a kill criterion and carries no K-code (`CLAUDE.md` Hard
Rule 4). No linter can see the difference between a threshold that works and one that got
lucky; only the person who chose it can, and only if they are asked.

The correct response to "this gate caught the bug" is **"by what mechanism?"** — before
believing it.
