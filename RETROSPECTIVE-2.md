# RETROSPECTIVE 2 — 2026-07-28, after H-012

The first retrospective was written after H-007 and extended through H-010. This one is
written after the feature slice returned, and it answers a different question. The first
asked *what does the project now know*. This one asks **what may the project now assert,
at what strength, and is there anything left worth testing.**

Four claims have been rejected: H-007, H-009, H-010, H-012. One was accepted and its
reading withdrawn: H-003. One gate stands: H-002. `EVALUATION.md` §2's ladder is halted at
rung 2 and has been since H-007.

Everything below is `[MEASURED]` with provenance, or is explicitly a judgement. §6 states a
position and §7 makes the case for stopping.

---

## 1. What has been measured about this instrument, at this resolution, on this feed

### 1.1 No deterministic feature set tried has carried directional information

Three attempts, three designs, three horizons, all negative:

| claim | design | horizon(s) | primary result | threshold | verdict |
|---|---|---|---|---|---|
| H-003 → H-007 | 3 features, 4 param, trading arms | 24 | `+0.060398 R` over random entry, `p = 0.0204` — **entirely long bias**: always-long matched it at `−0.000141 R`, `p = 0.5041` | rung 2 | reading withdrawn |
| H-012 | 10 features, 11 param, probability quality | 4, 24, 120 | BSS `+0.001848`, `−0.004939`, `+0.003015` | `+0.010` | REJECTED |
| H-012 ablation | each of 7 priors alone | 4, 24, 120 | best arm `+log_return_480` at `H = 120`, `+0.007025`, `p = 0.0959` | `+0.010`, `p ≤ 0.00833` | none cleared |

**The strongest single number anywhere in the directional search is `BSS +0.007025`** — one
ablation arm, at the one horizon whose per-fold structure cannot be examined, with a
`p`-value an order of magnitude above its threshold.

### 1.2 The dominant structure in the label is the base rate, and models keep finding it

`[MEASURED]`, H-012:

| horizon | base rate | 3-feature long share | 10-feature long share | 3-feature accuracy | always-long accuracy |
|---|---:|---:|---:|---:|---:|
| 4 | 0.5173 | 0.4991 | 0.5428 | 0.5337 | 0.5173 |
| 24 | 0.5369 | 0.5575 | 0.6209 | **0.5354** | 0.5369 |
| 120 | 0.5551 | **0.9265** | 0.7574 | **0.5478** | 0.5551 |

Always-long's directional accuracy **is** the base rate. At `H = 24` and `H = 120` the
three-feature model scores *below* it. **A model fitted on real labels is worse than
calling the majority class every time**, at two of three horizons.

At `H = 120` the three-feature model calls long on 92.65% of decisions. H-003's 56.2% was
the confound that took two hypotheses to expose; this is the same thing, larger, and
visible in one table.

### 1.3 Fitting real labels costs skill relative to fitting noise

`[MEASURED]`, H-001's unshuffled control against its own shuffled null:

> BSS `−0.006766` on true labels; shuffled-label null mean `−0.000855` across 30 seeds.

**Roughly eight times more out-of-sample skill is lost fitting the real relationship than
fitting a permuted one.** That is the signature of a model finding nothing and paying
variance for the search.

### 1.4 One real effect exists, and it is below the project's own floor

`[MEASURED]`, H-009: forward realised volatility is forecastable from these features.

> BSS `+0.024157`, `p = 0.0150`, n = 1,333. `realized_vol_24` alone scores `+0.023485` —
> **97.2% of the total**. Four registered predictions confirmed, including the sign in
> 5 of 5 folds.

Rejected against a registered threshold of `0.05`. The mechanism is confirmed; the
magnitude is not. **This is the only place in the project where a pre-registered
prediction about a mechanism was confirmed.**

### 1.5 Every measured horizon shows the same per-fold shape

`[MEASURED]`, H-012 full set:

| horizon | per-fold BSS |
|---|---|
| 4 | `+0.041436, +0.004709, −0.009625, −0.028047, −0.007495` |
| 24 | `+0.048762, +0.012931, −0.042581, −0.042214, −0.014213` |

Positive in the early folds, negative in the later ones, declining monotonically through
fold 3. H-003 showed it in R-space; H-012 shows it in probability space at two horizons.
**The pooled figures are mixtures of opposing regimes, not small stable effects** — and the
consistency of the shape across horizons and metrics is itself a finding.

### 1.6 Instrument facts established along the way

- The clock is New York's, not UTC's — weekly close at 20:00 UTC on 364 weeks and 21:00 on
  184, following US DST exactly.
- 3,835 gaps attributed; **6 unexplained**, poisoning 12 bars.
- Costs are not calibratable: genuine bid/ask ticks cover 0.40 years against 10.87 usable.
- The feed advertises 18.38 years; 10.87 carry more than one bar a day.
- Eleven parameters of real features converge at 1,000 gradient steps; twenty parameters of
  polynomial basis do not. **Conditioning, not parameter count.**

---

## 2. What remains untested, named individually

Each of these is a live gap. None is closed by anything above, and no result in this
project may be reported as if it were.

### 2.1 Capacity

**Untested.** H-011 registered three pre-committed statements — magnitude, sign,
attribution — and none was ever evaluated. No number exists.

**And the reason recorded for abandoning it was partly wrong**, corrected in H-011's entry
and in RETROSPECTIVE §7.1 on the same day: H-012 showed the optimiser problem was a
property of the polynomial basis, not of parameter count, so capacity was **not**
computationally unanswerable in general. The abandonment stands on one ground only — *three
columns is a very small hypothesis class regardless of what is fitted over it* — plus the
argument about not spending an independent anchor. Anyone citing the abandonment must cite
that ground and not tractability.

`N_claims` still carries H-011's draw. The question was asked; it was not answered.

### 2.2 Features beyond the ten tried

**Untested, and unbounded.** H-012's seven were priors with stated reasons, which is what
made it a hypothesis rather than a search. That is also its limit: seven priors is seven
priors. Nothing here bounds what a different set might find, and nothing here licenses the
claim that "features do not work on this instrument" — only that *these ten* do not, at
*these three horizons*, on *this feed*.

### 2.3 Session-relative features, blocked by R-001

**Structurally blocked, not merely untried.** `tests/test_causality.py` refuses any
registry entry declaring `session_relative=True` while R-001 is open, and the index-scramble
test falsifies the declaration rather than trusting it.

R-001 is open because the session eras — the daily break absent from 2017-10-07 to
2022-10-20 — have never been checked against FxPro's own announcements. Re-deriving them
from the feed is circular and is refused at the point someone would reach for it.

**This is the largest untested feature family**, and everything about intraday structure —
session opens, position within session, time until the break — lives in it.

### 2.4 The 2015-09-11 era, never evaluated out of sample

`[MEASURED]`, and it cannot be fixed under the current split rule:

| era | bars | ever in a test window? |
|---|---:|---|
| `2015-09-11` | 12,250 | **never, at any horizon** |
| `2017-10-07` | 30,945 | folds 0 and 1 |
| `2022-10-21` | 22,200 | folds 1–4 |

`first_test_start` is bar 32,697; the first era ends at 12,250. **18.7% of the in-window
series is training data only and always will be** at `FIRST_TEST_FRACTION = 0.50`. Every
out-of-sample claim this project has made is a claim about two eras, not three.

R-001's exposure is narrower than it looks and worth recording precisely: only one era
boundary falls inside any test window, so an error in the era derivation would affect
**fold 1's composition alone**. Folds 0 and 2–4 are single-era at every horizon.

### 2.5 `H = 120`'s per-fold blindness

`[MEASURED]`: 53–55 decisions per fold against a K-6 floor of 150. **All five folds below**,
pooled `n = 272` clearing K-6 by only 1.8×.

The per-fold sign-stability check — the diagnostic that caught H-003's fold-3 reversal and
that §1.5 above relies on entirely — **cannot run at that horizon.** A pooled figure there
cannot distinguish a small stable effect from two opposing regimes cancelling. H-012 §C
pre-committed to that before the run, and the run made it concrete: the best ablation arm
in the whole project sits at `H = 120`, where it cannot be examined.

---

## 3. Gates: which are blind, and at what boundary

### 3.1 K-1 — the boundary is now measured, and it is not where §6 predicted

`REPRODUCIBILITY.md` §6 said `train_test_overlap` "becomes detectable as capacity grows".
H-010 measured it at six capacities. Excess over the clean null at the same rung:

| parameters | 4 | 7 | 10 | 20 | 35 | 56 |
|---|---:|---:|---:|---:|---:|---:|
| excess | +0.000489 | +0.000805 | +0.000994 | **+0.001679** | −0.000686 | −0.002176 |

**The mechanism is real and the conclusion is still negative.** The excess rises
monotonically and roughly triples from 4 to 20 parameters — and at 20 it is still **thirty
times short** of the 0.05 trip threshold. Above 20 it inverts because the estimator has
stopped fitting.

**The boundary: K-1 cannot see train/test overlap at any capacity reachable within the
polynomial-logistic family.** Closing it requires a different estimator family — the
gradient-boosted stacker `EVALUATION.md` §2 rung 7 names — which is a different change with
its own ID to earn. The blind spot stays open, now for a measured reason instead of an
assumed one.

`scaler_fit_on_all` is also silent, at every capacity, and always will be: it leaks feature
distribution and no label information. That silence is correct, not blind.

### 3.2 K-1 can also pass vacuously, and the boundary is 35 parameters

At C-4 (35 parameters) and C-5 (56) the clean null collapses to `−0.129314` and
`−0.390547`. K-1's three registered conditions all hold at those numbers and the gate
returns **PASS** — because the combiner has stopped producing usable probabilities, not
because no leak is present.

Corroborating: `target_encoding_on_all` falls from `+0.239` to `+0.084` between 4 and 56
parameters, within 1.7× of the trip threshold. **The instrument degrades toward silence**,
which is the direction that hides failures. Those passes are recorded as passes that must
not be cited.

### 3.3 Never evaluated

- **K-3** (BSS on sealed holdout) — 0 of 3 openings used. The holdout has never been opened.
- **K-7** (Deflated Sharpe) — DSR is not built. No claim has reported a Sharpe.
- **K-8** (live vs backtest calibration) — nothing has run live.

### 3.4 The gate that does not exist

**The thing that stopped this project is not in the §1 table.** `EVALUATION.md` §2 rung 2
is a baseline condition, not a kill criterion; K-4 covers rung 1 only, which H-003 passed.
`EVALUATION.md` §13 records this without adding a K-code retroactively, on the grounds that
a criterion written after the result it governs is a description of the past wearing the
costume of a rule.

### 3.5 Known-dark areas that bound every cost figure

- The cost model's event set reaches **2.83% of bars**; every other scheduled release is
  priced at the flat floor. The error is *optimistic*, bounded by K-5 and the breakeven
  spread, removed by neither.
- **H-005 open.** No result may be described as satisfying `EVALUATION.md` §10.
- **No economic calendar.** Nothing in the repository knows when CPI, FOMC or ECB land.

### 3.6 The archival policy has never been exercised, and the artefacts are ephemeral

Found while assembling this document, and it is the most consequential gap in it.

`REPRODUCIBILITY.md` §8 requires run manifests "retained for the project's full life", a
monthly cold-storage export, and a **quarterly restore drill** — "pick a random result from
≥ 3 months prior and reproduce it from the manifest alone. A reproducibility policy that is
never exercised is not a policy."

`[MEASURED]`: **`runs/` is in `.gitignore`.** No manifest, no decision log and no result
file has ever been committed. What is version-controlled is the **sha256 of each manifest,
recorded in its `HYPOTHESES.md` entry** — and nothing else.

That design is defensible: hashes are the record, artefacts are outputs. But the
consequences are concrete and are not written down anywhere else:

- **No cold-storage export exists. No restore drill has been run.** Zero of the §8
  obligations have been discharged.
- The manifests live on one ephemeral container's disk. **H-009's manifest,
  `dc0f40bc-422c-433f-8790-4567a0408843`, is already absent from it** — it was produced in a
  parallel session and is not on this filesystem. Its hash is in the registry; the file it
  hashes is gone.
- Present on disk now: 5 evaluation manifests (H-001, H-003, H-007 ×2, H-012), 2
  harness validations, and the H-010 and H-012 row data. All produced on clean trees. **None
  of it is in git.**

**A hash with nothing left to check it against is a weaker record than it looks.** It
proves a file existed with those contents; it cannot reproduce the number. This bears
directly on §7: "archive with the registry intact" is not currently a thing this repository
can do, and saying so is more useful than assuming it.

---

## 4. Instrument defects: seven, and the pattern held every time

The count is **seven**, not six — H-010 contributed two unrelated ones, which is the likely
source of any undercount.

| # | defect | caught by |
|---|---|---|
| 1 | gap census 223 → 73 → 7 → 2 | a published exchange calendar |
| 2 | the circular payrolls test — lookup key was the answer | tick counts read independently of labels |
| 3 | three UTC invariants that would have selected for the bug | IANA `zoneinfo`, a second anchor |
| 4 | `MIN_PEAK_SHARE = 0.30` firing for a reason nobody could state | a deliberately mutated DST rule |
| 5 | the breakeven solver's false precision — "1,076.2 ± 3.9" on a curve with three sign changes | a nine-point probe grid |
| 6 | K-1's **vacuous pass** at 35 and 56 parameters | the clean null measured beside the verdict |
| 7 | **separability** costing 426,723 iterations against 314 at identical conditioning | an independent IRLS solve |

**The pattern, unchanged across all seven:**

- Every one was **fluent**. No warning, no `NaN`, no stack trace.
- **Four of seven had a self-check that agreed with them**, because the self-check shared
  the assumption. In #6 the self-check *was the gate*, returning PASS.
- **None was caught by re-reading the code.** Each needed an external reference or an
  adversarial fixture: a published calendar, `zoneinfo`, a corrupted input, a probe grid, a
  second solver.
- **Five of seven made the data look worse than it is**, not better. The failure mode is not
  optimism. It is confidence.
- **Two of seven were inside machinery written to prevent a defect** — the probe grid and
  the convergence rule. Instrument count is not monotone in instrument care.

**H-012 added none, and the reason sharpens the pattern.** Its one failure was
`frame_sha256` raising on a string column: a traceback, at the manifest step, after every
measurement had completed. **Loud failures are not in this table.** The table is a list of
things that computed successfully and were wrong, which is why `EVALUATION.md` §14 asks for
an external anchor rather than for more error handling.

---

## 5. What may be asserted, and at what strength

| assertion | strength |
|---|---|
| These ten features carry no directional information at `H ∈ {4, 24, 120}` on this feed | **measured**, pre-registered, four no-conditions, three horizons |
| The three-feature model's apparent edge was long bias | **measured**, H-007, `p = 0.5041` against always-long |
| These features forecast volatility, sub-threshold | **measured**, H-009, `+0.024157`, `p = 0.0150`, mechanism confirmed 5/5 |
| K-1 cannot detect train/test overlap in this estimator family | **measured** at six capacities |
| Gold is unpredictable at these horizons | **not asserted.** Nothing here supports it |
| Larger combiners would not help | **not asserted.** Untested — §2.1 |
| Other feature families would not help | **not asserted.** Untested — §2.2, §2.3 |

---

## 6. The honest position on the original question

**Does this instrument, at this horizon, carry directional information a deterministic
feature set can extract?**

**On the evidence: no, and the evidence is now reasonably strong for the space searched.**

What makes it stronger than a single null:

1. **Three independent designs failed** — trading arms in R-space, probability quality on
   ten features, and seven single-feature ablations — with no arm approaching its threshold.
2. **Three horizons failed**, spanning 4 hours to 5 days, a 30× range fixed before the run.
3. **The one confirmed mechanism is volatility, not direction** — and it was found by the
   same features and the same four parameters that found nothing directional. The instrument
   demonstrably *can* extract structure when structure is there.
4. **The failures have a consistent shape**: a model that finds the base rate, calls the
   majority class, and loses out-of-sample skill relative to fitting noise.

What keeps it from being decisive:

1. **The search space is small.** Ten features on one instrument at one resolution.
2. **The largest feature family is structurally blocked** by R-001, not tested and rejected.
3. **Capacity is untested**, and the recorded reason for abandoning it was partly wrong.
4. **18.7% of the window has never been evaluated out of sample** and cannot be under this
   split.

**The honest summary: the project has strong evidence for a narrow claim and weak evidence
for the broad one.** "These features do not work here" is well supported. "Nothing works
here" is not supported and has never been tested.

---

## 7. The case for stopping

`RESEARCH.md` §8 was written for this moment:

> If the protocol concludes that the system has no edge, the correct action is to publish
> that result internally, archive the repository, and stop. A well-executed negative result
> is a successful project. Time saved is the return.
>
> The failure mode this document exists to prevent is not losing money. It is spending two
> years unable to answer the question *"do we actually have an edge?"*

**That question has been answered for the space searched, in under a month, with a
registry that made every answer auditable.** By §8's own standard this is a success, and
the argument for stopping is straightforward:

**What stopping now costs.** Four named untested directions (§2). Each is real, and none is
cheap: R-001 needs an external source this project cannot generate; the 2015 era needs a
different split rule and therefore a new geometry registration; capacity needs a
well-conditioned design and a fresh `N_claims` draw; more features are unbounded by
construction.

**What continuing costs.** `N_claims` is 6 and the rank-1 BH critical value is `0.00833`.
Every further claim tightens it: at 7 it is `0.00714`, at 10 it is `0.005`. **The
multiple-testing budget is the scarcest resource here and it only shrinks.** A project
that keeps asking until something clears is the machine `EVALUATION.md` §9 exists to
prevent, and the registry makes that visible rather than preventing it.

**The strongest argument for stopping is not the evidence. It is the prior.** The
falsification criteria in H-012 §A were written before any feature was named, precisely so
this decision could be made on pre-committed terms. All four held. Reaching for the fifth
direction after four rejections is the behaviour those criteria were written to constrain,
and the fact that the untested directions are individually defensible does not change what
the sequence looks like.

**What would justify continuing, stated so it can be checked rather than argued:** a
*reason to expect* a specific untested direction to work, arrived at independently of the
fact that everything else failed. R-001 closing against a broker announcement would be one:
it would unblock the session-relative family on an external fact rather than on a wish. An
independent second feed would be another. **"We have not tried X yet" is not such a
reason**, and it is the only reason currently available for any of the four.

**Recommendation, stated as a judgement and not as a measurement: stop.** The four
rejections, the seven instrument defects, the two open review items, and the five named
untested directions are the deliverable. The `N_claims` denominator and the pre-committed
thresholds are what make the negative result worth something, and they only retain that
value if nothing further is drawn against them without a reason that is not "one more idea".

**One thing stopping requires, and it is not optional.** §3.6: `runs/` is gitignored, no
cold-storage export exists, and no restore drill has ever run. "Archive with the registry
intact" is not currently something this repository can do — the registry survives, the
artefacts it hashes do not, and one of them is already gone. **Discharging
`REPRODUCIBILITY.md` §8 once — export the manifests, run one restore drill, commit the
result — is the work that turns this from a set of claims into an archive.** It is
engineering hygiene, not a hypothesis: no registration, no `N_claims` draw, and it should
happen whether or not anything else does.

Beyond that, no next slice is proposed here. That is the point.

---

## 8. Counters at the close

```
Registered ......... 12     Accepted 2 (H-001, H-003 — reading withdrawn)
                            Rejected 4 (H-007, H-009, H-010, H-012)
                            Standing 1 (H-002)
                            In flight 5
N_claims ........... 6      H-003, H-004, H-007, H-009, H-011, H-012
  BH rank-1 ........ 0.00833
Holdout ............ 0 / 3 openings used
Runs ............... 5 evaluation manifests + 2 harness validations on disk, all on
                     clean trees. NONE version-controlled -- runs/ is gitignored and
                     only the sha256s are in the registry. See §3.6.
Open review items .. R-001 (session eras), H-005 (spread not calibratable)
Archival ........... REPRODUCIBILITY.md §8: 0 exports, 0 restore drills. Never exercised.
```

Build Order steps 1–6 are complete. **Step 7 — the first agent — was never licensed**, and
on the evidence above it should not be: `EVALUATION.md` §2 makes rungs 3–5 meaningless
until rung 2 is passed, and rung 2 was failed by a model that could not beat always-long.
