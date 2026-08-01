# RETROSPECTIVE 2 — 2026-07-28, after H-012

The first retrospective was written after H-007 and extended through H-010. This one is
written after the feature slice returned, and it answers a different question. The first
asked *what does the project now know*. This one asks **what may the project now assert,
at what strength, and is there anything left worth testing.**

Four claims have been rejected: H-007, H-009, H-010, H-012. One was accepted and its
reading withdrawn: H-003. One gate stands: H-002. `EVALUATION.md` §2's ladder is halted at
rung 2 and has been since H-007.

Everything below is `[MEASURED]` with provenance, or is explicitly a judgement. §1 is the
finding, §7 states a position, §8 makes the case for stopping, and §10 is the final
state of the registry.

---

## 1. The archival gap — the finding, and what discharging it showed

**This is first because it is the most consequential thing in this document, and because
it was found while assembling it rather than by any gate.**

### 1.1 What was wrong

`REPRODUCIBILITY.md` §8 requires run manifests "retained for the project's full life", a
monthly cold-storage export, and a **quarterly restore drill** — "pick a random result from
≥ 3 months prior and reproduce it from the manifest alone. A reproducibility policy that is
never exercised is not a policy."

`[MEASURED]`: **`runs/` was in `.gitignore`.** No manifest, decision log or result file had
ever been committed. What was version-controlled was the **sha256 of each manifest, recorded
in its `HYPOTHESES.md` entry** — and nothing else. Zero of §8's obligations had been
discharged: no export, no drill, no retention.

### 1.2 Why §8 escaped, and the transferable lesson

Every rule in this project that survived became a **build-failing test**:

| rule | enforcement |
|---|---|
| `DATA_CONTRACT.md` §1 causality | `tests/causality.py`, swept per feature, per seed |
| feature registry completeness | filesystem vs declaration, `tests/test_causality.py` |
| `REPRODUCIBILITY.md` §6 K-1 sensitivity | capacity signature, measured not read |
| R-001 session-relative block | registry refusal, with the declaration falsified |
| H-005 spread floor | `CostModel.__post_init__` refuses a lower floor |
| **`REPRODUCIBILITY.md` §8 archival** | **prose** |

**§8 is the only one that stayed prose, and it is the only one that was not obeyed.** Not
through disagreement or oversight in any single moment — nothing ever asked. The rule was
written, read, and quoted in a retrospective while being violated by the `.gitignore` three
directories away.

**The transferable lesson: a rule that is not a test is a rule you are relying on luck to
follow.** It survives exactly as long as nobody does the ordinary thing that breaks it —
here, adding `runs/` to `.gitignore`, which is what one does with output directories. That
is not a lapse in discipline. It is what happens to prose.

### 1.3 The discharge — verified, not asserted

Every manifest the registry references by hash, checked against the file before committing:

| run | hypothesis | recorded sha256 | verdict |
|---|---|---|---|
| `13ae20a1` | H-003 | `53cde12e…` | **MATCH** |
| `8838059a` | H-001 | `b6daca9a…` | **MATCH** |
| `ab8dfbcb` | H-007 | `2f02739a…` | **MATCH** |
| `bd93b544` | H-012 | `49938ebe…` | **MATCH** |
| `dc0f40bc` | **H-009** | `0c2ed357…` | **FILE ABSENT** |

Four of five verify exactly. Now committed, along with two harness-validation manifests,
H-003's 4.2 MB decision log, and the H-010 and H-012 row data.

`src/evaluation/archive.py` parses every `**Run manifest:**` reference out of the registry
and `tests/evaluation/test_archive.py` fails the build when a hash has no file behind it,
when a file does not match its hash, or when `runs/` is gitignored again. Same shape as the
guards that worked.

### 1.4 The loss, named

**H-009's manifest is unrecoverable.** Run `dc0f40bc-422c-433f-8790-4567a0408843`, executed
2026-07-28 at commit `ea4dc33` on a clean tree, in a session whose filesystem is gone. It
was never committed because `runs/` was ignored.

**What survives:** the sha256 in H-009's entry, the full result block, the code at
`ea4dc33`, and the snapshot hash. Together those are enough to **re-run** H-009. They are
not enough to **verify that a re-run reproduces the original**, because the artefact the
recorded hash refers to no longer exists to be compared against.

`archive.KNOWN_LOST` records this, and the guard checks the record from both sides: an entry
whose file exists fails the build as loudly as a missing file with no entry.

### 1.5 The restore drill, run once

§8's letter asks for a result "≥ 3 months prior". **The project is eleven days old, so that
criterion cannot be met and is recorded as unmet rather than reinterpreted.** The drill ran
on the oldest evaluation run instead: **H-001, `8838059a`, 2026-07-27**.

Method — from the manifest alone: check out the recorded commit
`ae3362159628807b9671e4e2d46c73c0c4142d47` into a clean worktree, build the environment from
the locked file at that commit, restore the snapshot, re-run, compare.

Preconditions verified before running:

| | recorded in manifest | at that commit |
|---|---|---|
| `env_lock_sha256` | `ff88c884…` | `ff88c884…` **match** |
| `data_snapshot_sha256` | `71f9fcf1…` | `71f9fcf1…` **match** |

**Result — every reported number reproduces:**

| quantity | recorded 2026-07-27 | drill |
|---|---|---|
| mean BSS, 30 seeds | `−0.000855` | `−0.000855` |
| 95% CI upper | `−0.000577` | `−0.000577` |
| median BSS | `−0.000734` | `−0.000734` |
| max BSS | `+0.000757` | `+0.000757` |
| min / sd | `−0.002799` / `0.000815` | `−0.002799` / `0.000815` |
| unshuffled control | `−0.006766`, n = 1,364 | `−0.006766`, n = 1,364 |
| verdict | K-1 PASSES | K-1 PASSES |

**The drill passes.** Two things it also showed, both worth recording:

- **Hard Rule 10 fired, correctly.** The first attempt refused to start — "REFUSING TO RUN:
  the git tree is dirty" — because the drill's own setup left an untracked path. The gate
  did its job against a run it had never seen.
- **A manifest's hash is not itself reproducible, and should not be read as if it were.**
  The drill's manifest is `6ee1d776…`, not `8838059a…`, because `run_id` is a fresh UUID and
  the timestamp differs. The recorded sha256 proves *file integrity*; it does not and cannot
  prove *run reproducibility*. Those are different properties and only the second is what
  §8's drill establishes.

---

## 2. What has been measured about this instrument, at this resolution, on this feed

### 2.1 No deterministic feature set tried has carried directional information

Three attempts, three designs, three horizons, all negative:

| claim | design | horizon(s) | primary result | threshold | verdict |
|---|---|---|---|---|---|
| H-003 → H-007 | 3 features, 4 param, trading arms | 24 | `+0.060398 R` over random entry, `p = 0.0204` — **entirely long bias**: always-long matched it at `−0.000141 R`, `p = 0.5041` | rung 2 | reading withdrawn |
| H-012 | 10 features, 11 param, probability quality | 4, 24, 120 | BSS `+0.001848`, `−0.004939`, `+0.003015` | `+0.010` | REJECTED |
| H-012 ablation | each of 7 priors alone | 4, 24, 120 | best arm `+log_return_480` at `H = 120`, `+0.007025`, `p = 0.0959` | `+0.010`, `p ≤ 0.00833` | none cleared |

**The strongest single number anywhere in the directional search is `BSS +0.007025`** — one
ablation arm, at the one horizon whose per-fold structure cannot be examined, with a
`p`-value an order of magnitude above its threshold.

### 2.2 The dominant structure in the label is the base rate, and models keep finding it

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

### 2.3 Fitting real labels costs skill relative to fitting noise

`[MEASURED]`, H-001's unshuffled control against its own shuffled null:

> BSS `−0.006766` on true labels; shuffled-label null mean `−0.000855` across 30 seeds.

**Roughly eight times more out-of-sample skill is lost fitting the real relationship than
fitting a permuted one.** That is the signature of a model finding nothing and paying
variance for the search.

### 2.4 One real effect exists, and it is below the project's own floor

`[MEASURED]`, H-009: forward realised volatility is forecastable from these features.

> BSS `+0.024157`, `p = 0.0150`, n = 1,333. `realized_vol_24` alone scores `+0.023485` —
> **97.2% of the total**. Four registered predictions confirmed, including the sign in
> 5 of 5 folds.

Rejected against a registered threshold of `0.05`. The mechanism is confirmed; the
magnitude is not. **This is the only place in the project where a pre-registered
prediction about a mechanism was confirmed.**

### 2.5 Every measured horizon shows the same per-fold shape

`[MEASURED]`, H-012 full set:

| horizon | per-fold BSS |
|---|---|
| 4 | `+0.041436, +0.004709, −0.009625, −0.028047, −0.007495` |
| 24 | `+0.048762, +0.012931, −0.042581, −0.042214, −0.014213` |

Positive in the early folds, negative in the later ones, declining monotonically through
fold 3. H-003 showed it in R-space; H-012 shows it in probability space at two horizons.
**The pooled figures are mixtures of opposing regimes, not small stable effects** — and the
consistency of the shape across horizons and metrics is itself a finding.

### 2.6 Instrument facts established along the way

- The clock is New York's, not UTC's — weekly close at 20:00 UTC on 364 weeks and 21:00 on
  184, following US DST exactly.
- 3,835 gaps attributed; **6 unexplained**, poisoning 12 bars.
- Costs are not calibratable: genuine bid/ask ticks cover 0.40 years against 10.87 usable.
- The feed advertises 18.38 years; 10.87 carry more than one bar a day.
- Eleven parameters of real features converge at 1,000 gradient steps; twenty parameters of
  polynomial basis do not. **Conditioning, not parameter count.**

---

## 3. What remains untested, named individually

Each of these is a live gap. None is closed by anything above, and no result in this
project may be reported as if it were.

### 3.1 Capacity

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

### 3.2 Features beyond the ten tried

**Untested, and unbounded.** H-012's seven were priors with stated reasons, which is what
made it a hypothesis rather than a search. That is also its limit: seven priors is seven
priors. Nothing here bounds what a different set might find, and nothing here licenses the
claim that "features do not work on this instrument" — only that *these ten* do not, at
*these three horizons*, on *this feed*.

### 3.3 Session-relative features, blocked by R-001

**Structurally blocked, not merely untried.** `tests/test_causality.py` refuses any
registry entry declaring `session_relative=True` while R-001 is open, and the index-scramble
test falsifies the declaration rather than trusting it.

R-001 is open because the session eras — the daily break absent from 2017-10-07 to
2022-10-20 — have never been checked against FxPro's own announcements. Re-deriving them
from the feed is circular and is refused at the point someone would reach for it.

**This is the largest untested feature family**, and everything about intraday structure —
session opens, position within session, time until the break — lives in it.

### 3.4 The 2015-09-11 era, never evaluated out of sample

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

### 3.5 `H = 120`'s per-fold blindness

`[MEASURED]`: 53–55 decisions per fold against a K-6 floor of 150. **All five folds below**,
pooled `n = 272` clearing K-6 by only 1.8×.

The per-fold sign-stability check — the diagnostic that caught H-003's fold-3 reversal and
that §2.5 above relies on entirely — **cannot run at that horizon.** A pooled figure there
cannot distinguish a small stable effect from two opposing regimes cancelling. H-012 §C
pre-committed to that before the run, and the run made it concrete: the best ablation arm
in the whole project sits at `H = 120`, where it cannot be examined.

---

## 4. Gates: which are blind, and at what boundary

### 4.1 K-1 — the boundary is now measured, and it is not where §6 predicted

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

### 4.2 K-1 can also pass vacuously, and the boundary is 35 parameters

At C-4 (35 parameters) and C-5 (56) the clean null collapses to `−0.129314` and
`−0.390547`. K-1's three registered conditions all hold at those numbers and the gate
returns **PASS** — because the combiner has stopped producing usable probabilities, not
because no leak is present.

Corroborating: `target_encoding_on_all` falls from `+0.239` to `+0.084` between 4 and 56
parameters, within 1.7× of the trip threshold. **The instrument degrades toward silence**,
which is the direction that hides failures. Those passes are recorded as passes that must
not be cited.

### 4.3 Never evaluated

- **K-3** (BSS on sealed holdout) — 0 of 3 openings used. The holdout has never been opened.
- **K-7** (Deflated Sharpe) — DSR is not built. No claim has reported a Sharpe.
- **K-8** (live vs backtest calibration) — nothing has run live.

### 4.4 The gate that does not exist

**The thing that stopped this project is not in the §1 table.** `EVALUATION.md` §2 rung 2
is a baseline condition, not a kill criterion; K-4 covers rung 1 only, which H-003 passed.
`EVALUATION.md` §13 records this without adding a K-code retroactively, on the grounds that
a criterion written after the result it governs is a description of the past wearing the
costume of a rule.

### 4.5 Known-dark areas that bound every cost figure

- The cost model's event set reaches **2.83% of bars**; every other scheduled release is
  priced at the flat floor. The error is *optimistic*, bounded by K-5 and the breakeven
  spread, removed by neither.
- **H-005 open.** No result may be described as satisfying `EVALUATION.md` §10.
- **No economic calendar.** Nothing in the repository knows when CPI, FOMC or ECB land.

---

## 5. Instrument defects: nine, and the pattern held every time

The count is **nine**. Seven were defects in code. **The eighth, added 2026-07-29, is a
defect in a *claim about* code** — and it is the only one that reached a merged commit.
**The ninth, added 2026-08-01, is neither**: correct code printing a correct number
that could not be checked from what was printed. See §5.2.

| # | defect | caught by |
|---|---|---|
| 1 | gap census 223 → 73 → 7 → 2 | a published exchange calendar |
| 2 | the circular payrolls test — lookup key was the answer | tick counts read independently of labels |
| 3 | three UTC invariants that would have selected for the bug | IANA `zoneinfo`, a second anchor |
| 4 | `MIN_PEAK_SHARE = 0.30` firing for a reason nobody could state | a deliberately mutated DST rule |
| 5 | the breakeven solver's false precision — "1,076.2 ± 3.9" on a curve with three sign changes | a nine-point probe grid |
| 6 | K-1's **vacuous pass** at 35 and 56 parameters | the clean null measured beside the verdict |
| 7 | **separability** costing 426,723 iterations against 314 at identical conditioning | an independent IRLS solve |
| 8 | **`rollovers_crossed` "counts five rollovers a week"** — it counts seven | running the function on a known week |
| 9 | **a `3.64x` divergence printed with no denominator** — a per-calendar-day figure read as a per-night one | reconstructing the number from the raw charge |

**The pattern, unchanged across all nine:**

- Every one was **fluent**. No warning, no `NaN`, no stack trace.
- **Four of nine had a self-check that agreed with them**, because the self-check shared
  the assumption. In #6 the self-check *was the gate*, returning PASS.
- **None was caught by re-reading the code.** Each needed an external reference or an
  adversarial fixture: a published calendar, `zoneinfo`, a corrupted input, a probe grid, a
  second solver — for #8, simply calling the function, and for #9, recomputing the printed
  number from the charge it came from.
- **Five of nine made the data look worse than it is**, not better. The failure mode is not
  optimism. It is confidence.
- **Three of nine were inside machinery written to prevent a defect** — the probe grid, the
  convergence rule, and the divergence report itself. Instrument count is not monotone in
  instrument care.

### 5.1 Why #8 is a different kind, and the worse kind

Defects 1-7 were wrong **code**. #8 was correct code with a wrong **sentence about it**, in
a docstring, in a constant's comment, in a PR body, and in `CLAUDE.md`. Three consequences
follow that the first seven do not have.

**It could not fail.** A wrong computation eventually meets an input that embarrasses it.
A wrong sentence computes nothing, so nothing can contradict it. The only thing that ever
would have was somebody running `rollovers_crossed` on a known week, which took one
command.

**It propagated through review.** #1-7 were caught before or during the run that used them.
#8 was written, reviewed, described in a merged pull request, and copied into three more
documents — each copy making it look better attested. **The number of places a claim
appears is not evidence for it**, and this project now has an instance where it looked
like evidence.

**Its blast radius was arithmetic downstream.** It inflated the reported weekly divergence
by 7/5 and produced a specific false claim — that a broker charging 15 points a night
already exceeds the registry — which is exactly the kind of headline number that gets
quoted onward.

**The lesson, and it generalises §1.2 rather than repeating it.** §1.2: *a rule that is not
a test is a rule you are relying on luck to follow.* One step out: **an assertion about
someone else's code, with no test behind it, is an assertion you are relying on luck for.**
The fix is the same shape and took four lines — `tests/risk/test_clock.py` now calls
`rollovers_crossed` over a Monday-to-Monday span and asserts 7, over a fortnight and
asserts 14, and over a weekend and asserts 3. Any change to that function now fails the
build in the layer that depends on it.

**Where the pattern was already visible.** `mt5_probe.py`'s correction log says it exactly:
*"a measurement tool manufactures findings until the tool itself is tested."* #8 is the
same sentence with "measurement tool" replaced by "claim". Both were fluent, both were
internally consistent, and both were wrong.

**H-012 added none, and the reason sharpens the pattern.** Its one failure was
`frame_sha256` raising on a string column: a traceback, at the manifest step, after every
measurement had completed. **Loud failures are not in this table.** The table is a list of
things that computed successfully and were wrong, which is why `EVALUATION.md` §14 asks for
an external anchor rather than for more error handling.

---

### 5.2 Why #9 is neither code nor claim, and what it cost

Added 2026-08-01. `SwapDivergence` printed **`3.64x`** for the measured long side against
the registered substitute. The arithmetic was right, the code was right, and the number was
right. **It was still a defect**, because the row did not say what it had divided by.

`3.64x` is `13.58 charged / 1.87 elapsed calendar days`, expressed against a registered
constant of 20 points **per night**. On the per-night denominator the same charge reads
**`3.395x`**. Both are correct; only one shares the registry's unit; the printed row named
neither.

**What it cost.** The number was read as evidence that defect #8 was still live in the
tool's own output — that the retracted five-rollover denominator had survived into the alert
string — and a corrected figure of `2.60x` was derived from that premise. Neither was so.
The correction had reached the string, the arithmetic and the constants. And the reading is
self-refuting once the arithmetic is done: `2.60 x 140 = 364` points a week is **52.0 points
a night**, against the **67.9** that had just been measured. Under the five-night
denominator the tool would have printed **`5.10x`**, so `3.64x` was itself evidence the
correction had landed.

**Why this belongs in the table.** #1-7 computed the wrong number. #8 said the wrong thing
about a right number. #9 said nothing at all about a right number, and the silence was
enough for a careful reader — the person who had written the correction eight days earlier —
to reconstruct a wrong cause with confidence. **An output that cannot be audited from its own
face is an instrument defect even when every digit in it is correct.**

**Three things were wrong with the presentation and all three are fixed.**

1. The source column read `measured`. It now reads `measured/day` or `measured/night`, and
   both rows are printed whenever both denominators exist.
2. Only one basis was computed. `PositionCarry` now carries `rate_measured_per_night`
   alongside `rate_measured_per_day`, and the comparison runs on both.
3. Nothing said which to quote. A note now fires whenever the two ratios differ by more
   than 1% — deliberately *below* the measured route's own 10% tolerance, because the
   reading that motivated it differed by 7.2% and a threshold set at the tolerance would
   have stayed silent on exactly the case it exists for.

**The lesson, and it is the third step in the same direction.** §1.2: a rule that is not a
test is a rule you are relying on luck to follow. §5.1: an assertion about someone else's
code, with no test behind it, is an assertion you are relying on luck for. Now: **a number
whose units are not printed beside it is a number you are relying on luck to have read
correctly** — and the luck runs out fastest for the reader who knows the most, because they
have the most alternative explanations available to reach for.

`tests/risk/test_swap.py` and `tests/risk/test_report.py` reconstruct `3.64x`, `3.395x` and
the counterfactual `5.10x` from the raw charge, so all three numbers are pinned by tests
rather than by this section.

---

## 6. What may be asserted, and at what strength

| assertion | strength |
|---|---|
| These ten features carry no directional information at `H ∈ {4, 24, 120}` on this feed | **measured**, pre-registered, four no-conditions, three horizons |
| The three-feature model's apparent edge was long bias | **measured**, H-007, `p = 0.5041` against always-long |
| These features forecast volatility, sub-threshold | **measured**, H-009, `+0.024157`, `p = 0.0150`, mechanism confirmed 5/5 |
| K-1 cannot detect train/test overlap in this estimator family | **measured** at six capacities |
| Gold is unpredictable at these horizons | **not asserted.** Nothing here supports it |
| Larger combiners would not help | **not asserted.** Untested — §3.1 |
| Other feature families would not help | **not asserted.** Untested — §3.2, §3.3 |

---

## 7. The honest position on the original question

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

## 8. The case for stopping

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

**What stopping now costs.** Four named untested directions (§3). Each is real, and none is
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

**The one thing stopping required has been done.** §1: `runs/` is un-ignored and guarded,
every surviving manifest is committed and verified against its recorded hash, the single
unrecoverable loss is named, and the restore drill has been run once and passed. That was
engineering hygiene rather than a hypothesis — no registration, no `N_claims` draw — and it
is what turns this from a set of claims into an archive.

Beyond that, no next slice is proposed here. That is the point.

---

## 9. Counters at the close

```
Registered ......... 12     Accepted 2 (H-001, H-003 — reading withdrawn)
                            Rejected 4 (H-007, H-009, H-010, H-012)
                            Standing 1 (H-002)
                            In flight 5
N_claims ........... 6      H-003, H-004, H-007, H-009, H-011, H-012
  BH rank-1 ........ 0.00833
Holdout ............ 0 / 3 openings used
Runs ............... 5 evaluation manifests + 2 harness validations, all on clean trees,
                     all now committed and verified against their recorded hashes.
                     1 referenced manifest unrecoverable (H-009). See §1.
Open review items .. R-001 (session eras), H-005 (spread not calibratable)
Archival ........... REPRODUCIBILITY.md §8 discharged 2026-07-28: archive committed and
                     guarded, loss recorded, 1 restore drill run and passed.
```

Build Order steps 1–6 are complete. **Step 7 — the first agent — was never licensed**, and
on the evidence above it should not be: `EVALUATION.md` §2 makes rungs 3–5 meaningless
until rung 2 is passed, and rung 2 was failed by a model that could not beat always-long.

---

## 10. Final state of the registry

**For whoever picks this up.** Everything below is the state as of 2026-07-28. Nothing here
is in flight, nothing is waiting on a decision, and no work is proposed.

### 10.1 Every hypothesis, and exactly what it established

| ID | class | status | what it established |
|---|---|---|---|
| **H-001** | gate | **ACCEPTED** | K-1 does not trip. Shuffled-label null mean BSS `−0.000855` across 30 seeds. Reproduced by the §1.5 restore drill. Certifies *no label reaches the model along this path at this capacity* — not the absence of all leakage. |
| **H-002** | gate | **STANDING** | Temporal causality of every feature. Asserted on every commit. The day it fails is the day the pipeline halts. |
| **H-003** | claim | **ACCEPTED, reading withdrawn** | Signal beat random entry by `+0.060398 R`, `p = 0.0204`. The run stands as executed; **the directional inference does not** — H-007 showed the difference was long bias. **"Its arithmetic holds" was too strong and is corrected in §11**: the cost inputs are now measured to be wrong, though by 0.45% of the effect. Status left as ACCEPTED on purpose: the registry records what was done, not what is currently believed. |
| **H-004** | claim | **REGISTERED, never run** | LLM synthesis vs deterministic combination. Never reached — the ladder halted first. Carries an `N_claims` draw. |
| **H-005** | gate | **REGISTERED, open** | Registered deviation from `EVALUATION.md` §10: spread is not calibratable on this feed. **No result may be described as satisfying §10 while this is open.** The 75-point floor is raisable only. |
| **H-006** | gate | **REGISTERED** | The evaluation window `2015-09-11 → 2026-07-26` is a declared boundary, not a truncation. |
| **H-007** | claim | **REJECTED** | Always-long matched the signal: `−0.000141 R`, `p = 0.5041`. This is what stopped the project, and it is at a ladder rung with no K-code. |
| **H-008** | gate | **REGISTERED, unrun, sweep values fixed** | The 1.5× ATR stop/target sweep: **0.75, 1.0, 1.5, 2.0, 3.0**, fixed before any of them produced a number. Its Order clause makes it conditional on H-007 passing, which it did not. **The values stay fixed for whenever there is a directional reading to test the robustness of.** Not VOID — nothing about it was invalidated, its subject was. |
| **H-009** | claim | **REJECTED** | Volatility is forecastable: `BSS +0.024157`, `p = 0.0150`, mechanism confirmed 5/5 folds, `realized_vol_24` carrying 97.2%. Below the registered `0.05` floor. **Its manifest is the one unrecoverable artefact** — §1.4. |
| **H-010** | gate | **REJECTED** | K-1 re-measured at six capacities. Passes at 4/7/10 parameters; condition (iv) unsatisfiable at 20/35/56. Established that `train_test_overlap` is not detectable at any capacity in this estimator family, and that K-1 can pass *vacuously*. |
| **H-011** | claim | **REGISTERED, unrun, ABANDONED** | The capacity question. Three pre-committed statements, **none ever evaluated — no number exists.** Abandoned on the ground that three columns is a very small hypothesis class, **not** on tractability (that reasoning was corrected after H-012). **Its `N_claims` draw stands.** Capacity is untested and must never be reported as excluded. |
| **H-012** | claim | **REJECTED** | Ten features, eleven parameters, three horizons. All four pre-registered no-conditions hold. The answer is no for this feature set at these horizons. |

### 10.2 Counters

```
Registered ......... 12     Accepted 2 (H-001; H-003 — reading withdrawn)
                            Rejected 4 (H-007, H-009, H-010, H-012)
                            Standing 1 (H-002)
                            Registered and unrun 5 (H-004, H-005, H-006, H-008, H-011)
N_claims ........... 6      H-003, H-004, H-007, H-009, H-011, H-012
  BH rank-1 ........ 0.05 x 1/6 = 0.00833
Holdout ............ 0 / 3 openings used — never opened
Runs ............... 5 evaluation manifests + 2 harness validations, all on clean trees,
                     all committed. 1 referenced manifest unrecoverable (H-009).
Restore drills ..... 1, passed (H-001, §1.5)
```

**Nothing in the family clears `EVALUATION.md` §9.** At `m = 6` the step-up finds `k = 2`:
H-009 at `0.0150` and H-003 at `0.0204 ≤ 0.025`. Both clear the correction; neither reading
survives on substance — H-009 failed its magnitude threshold and H-003's direction was
withdrawn by H-007.

### 10.3 Open review items — both stay open

- **R-001** — `session.eras` has never been checked against an external source. **Blocking
  condition intact**: `tests/test_causality.py` refuses any feature declaring
  `session_relative=True` while it is open, and the index-scramble test falsifies that
  declaration rather than trusting it. Re-deriving the eras from the feed does not close it
  and is refused at the point someone would reach for it. Closing it needs an FxPro
  announcement or equivalent external source.
- **H-005** — spread is not calibratable on this feed. Open. No §10 claim may be made.

### 10.4 What a reader must not conclude

Three statements are easy to reach and none is supported:

1. **"Gold is unpredictable at these horizons."** Not tested. Ten features on one instrument
   at one resolution is a small search.
2. **"A larger combiner would not help."** Not tested — §3.1. H-011's draw was spent asking;
   the question was never answered.
3. **"Capacity was excluded."** Explicitly false. It was **abandoned**, and the difference
   is recorded in H-011's entry precisely because it is the thing a later reader will
   collapse.

### 10.5 What is safe to conclude

- These ten features carry no directional information at `H ∈ {4, 24, 120}` on this feed,
  by four pre-registered criteria that were written before any feature was named.
- The three-feature model's apparent edge was long bias.
- These features forecast volatility, significantly, below the project's own floor.
- K-1 cannot detect train/test overlap in this estimator family, at any capacity reachable
  within it.
- The pipeline reproduces: H-001 was re-derived from its manifest alone, bit for bit.

### 10.6 If someone restarts this

Not a proposal — a statement of what the record obliges. Any new work starts by reading
`RESEARCH.md`, `DATA_CONTRACT.md`, `EVALUATION.md`, this file, and `HYPOTHESES.md` §0, and
by accepting that `N_claims` **starts at 6, not at 0**. The denominator does not reset
because someone new is looking. That is the whole reason it is written down.

---

## 11. The cost model, measured — a correction to §10 and to my own claim

**Dated 2026-07-29, after §10 was written.** `HYPOTHESES.md` H-005, H-003 and H-007 carry
the full records. This section exists because §10 states things that are now known to be
wrong, and §10 is the document a later reader is most likely to read alone.

### 11.1 What was measured

`scripts/risk_monitor.py --probe`, FxPro demo, `GOLD`: `swap_mode = 2`
(`SYMBOL_SWAP_MODE_CURRENCY_SYMBOL`), `swap_long = −67.9`, `swap_short = +27.0`.

The registered substitute is a **fixed points rate charged in both directions**. The
broker's terms are **price-dependent and directionally signed**. Those are different in
kind, and the difference is not something a better constant fixes.

**The refusal is the finding.** `risk.swap.declared_swap` would not convert a
base-currency rate without inventing a price, so it returned a `Refusal` naming the
structure. A default would have produced a plausible number and hidden a structural
mismatch. That is the third time in this project that a refusal has been the result —
§3.6, the `UNDETERMINED` DST verdict, and now this.

### 11.2 What it does to the two cost-dependent results

Arithmetic under stated assumptions, **not a re-run**. Both entries carry the full tables.

| | measured | corrected | change | as a share of its own 95% CI half-width |
|---|---|---|---|---|
| H-003, signal vs random | `+0.060398 R` | `≈ +0.060127 R` | `−0.000271 R` | negligible |
| H-007, signal vs always-long | `−0.000141 R` | `≈ +0.001596 R` | `+0.001737 R` | **2.4%** |

**H-007's point estimate flips sign.** That is the only correction in this project that
moves a number in the signal's favour, and it is recorded prominently for exactly that
reason — a record that buried it would be choosing which corrections to publish.

**It does not move the verdict**, and the bound comes from numbers already in the entry:
the correction is **2.4% of the recorded 95% CI half-width** of 0.0735 R. It moves a point
estimate that was indistinguishable from zero to another point estimate that is
indistinguishable from zero. It is also 2.6% of H-003's effect, and H-012 tested for
direction *directly* and did not find it. A financing correction cannot manufacture what a
direct test looked for and missed.

### 11.3 A claim of mine that was wrong

When `src/risk` was built I asserted that `backtest.costs.rollovers_crossed` "counts five
rollovers a week and has no triple-swap concept", so the registered model understated a
week's carry by two sevenths. **I asserted it from the function's name without reading its
body, and it is false.**

`[MEASURED]` it counts every calendar day's boundary, weekends included: 7 per week, 14
per fortnight. The registered night **count** is right. Only the timing differs, and it
cancels over whole weeks.

**The transferable part is in §5.1**, where this is recorded as **instrument defect #8** —
the first in the table that is a defect in a *claim about* code rather than in code, and
the only one that reached a merged commit. §1.2 recorded that a rule which is not a test is
a rule you are relying on luck to follow; this is the same failure one step out.
`tests/risk/test_clock.py` now measures the count against the real function, so the premise
fails the build rather than propagating.

### 11.4 What §10 should now be read as saying

- **§10.1, H-003** — "its arithmetic holds" is wrong. Its arithmetic executed as recorded;
  its cost inputs did not describe the broker. The correction is 0.45% of the effect.
- **§10.1, H-007** — REJECTED stands. Its point estimate flips sign under correction and
  remains inside noise.
- **§10.2 counters** — unchanged. `N_claims` stays at **6**. This is a broker measurement,
  not an evaluation run: no `hypothesis_id`, no draw, no re-run.
- **§10.5, "what is safe to conclude"** — the entry on the three-feature model's edge being
  long bias stands, and stands on H-007's substance rather than on its cost arithmetic.

### 11.5 What is still not measured

The magnitude in §11.1 rests on a reading of the mode-2 figures that the field alone cannot
confirm: 67.9 ounces a night per lot is not a possible charge, so the number is not
literally base-currency units at face value. Read as an effective deposit-currency charge
it annualises to **10.3%** against the registered **3.0%**, and only the first of those is
a plausible gold financing rate — which is evidence, not a measurement.

**One week of a real position settles it.** Until then the declared route stays refused and
`SwapDivergence` reports `UNAVAILABLE` on the declared side while still flagging
`bears_on_the_registry`, because the structure is enough on its own.

### 11.6 Two nights of it, 2026-08-01 — what came back and what did not

`[MEASURED]` a live 0.10-lot long was charged **13.58 across two charging events**: 6.79 a
night, **67.9 points per lot per night**, equal to the published `swap_long` to the digit.

**Settled.** The deposit-currency reading in §11.5 is now a measurement **on the long side**,
and the literal base-currency reading is dead — 67.9 ounces would have been about 277,000 at
the price it was read at. The divergence against the registered substitute is **3.395x per
night**, and that factor is what carries the whole H-007 correction, because always-long is
100% long.

**Not settled, and the distinction is the point.** The *structure* did not come back. A rate
proportional to price with its coefficient calibrated at the price on the night it was read
produces exactly the same charge; one price cannot separate a constant from a
proportionality through that point. The pre-committed instrument returned `UNDETERMINED`
and named the two conditions that failed — two charging events against five, and a monotone
price path against two reversals. **The condition that passed is the resolution one**: the
price moved far enough for a response to have been visible, and the window still could not
call it. That is a failure of shape, not of range, and no threshold was moved to reach it.

**Also not settled: the short side.** The +27.0 credit is still a published field with
nothing charged against it. Both cost-dependent corrections were re-run across both readings
of it and neither conclusion depends on which is true — H-007's sign flip survives even the
adverse reading. See `HYPOTHESES.md` H-003 and H-007, 2026-08-01.
