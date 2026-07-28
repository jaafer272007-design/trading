# RETROSPECTIVE — 2026-07-28, after H-007

**What this project now knows that it did not know before.** Not a summary of what
happened; a record of what has been established, what has been ruled out, and what is
still dark. Written while the runs are fresh, before any feature research begins, so that
the next phase argues with measurements rather than with recollections.

Scope: from the first raw export to the rejection of H-007. Two claims run, one gate
cleared, one gate standing, the ladder halted at rung 2.

Everything below is either `[MEASURED]` with its provenance or explicitly marked as a
judgement. Nothing here is an estimate presented as a finding — that failure mode is the
subject of §4.

---

## 1. What was measured, with provenance

**The instrument.** FxPro-MT5 Demo, symbol `GOLD`, H1 bars, exported through
`scripts/mt5_export.py` on a Windows terminal that this session never touched. Six raw
files, hashes pre-registered in `src/data/raw.py` before the bytes arrived, verified
against the committed bytes on landing.

**The snapshot.** Derived by `src/data/snapshot.py` from raw + frozen calendar + `src/data/`,
none of it committed and all of it reproducible:

| | |
|---|---|
| raw sha256 | `519ecd24515495bdeb7fb1df2a3699a98ac0337be91af87fe0b218516eb4b775` |
| calendar sha256 | `38114b46ded97a92e76e56d75b4dd923f1a6cded3c2e7b2ecfc2dbdb156bdd59` |
| derived sha256 | `71f9fcf1a2e2a46dc2136d2b4bbf1a7b43c2abcd5cfce1dfb9028c9b4ac028c6` |
| bars available | 67,367, first `2008-03-10T22:00Z` |
| bars in window | **65,395**, window `2015-09-11` → `2026-07-26` (H-006) |
| valid in window | 65,383 — **12 invalid bars**, from 6 unexplained gaps |
| labels valid | 65,215 at `H = 24` |
| eligible for evaluation | 64,886 |
| decisions on the registered grid | **1,364**, 272–273 per fold |

**The feed advertises 18.38 years; 10.87 of them carry more than one bar a day.** H-006
registers that boundary, so the shortfall is a declared decision rather than a truncation
discovered inside a run manifest.

**The gap census**, 3,835 gaps in the raw series, attributed:

| cause | count |
|---|---|
| `out_of_window` | 1,960 |
| `daily_break` | 1,227 |
| `weekend` | 568 |
| `early_close` | 66 |
| `holiday` | 8 |
| **`unknown`** | **6** |

Six. Everything else is the market being shut, and the distinction is load-bearing:
treating closures as defects would poison 3,700 of 3,835 gaps, and treating defects as
closures would absorb the six that matter.

**The session structure changes twice inside the window.** The feed's daily break is
absent from 2017-10-07 to 2022-10-20 and present either side. Recorded as
`session.eras` in the frozen calendar, carried as a first-class `session_era` column, and
**not externally verified** — `REVIEW_ITEMS.md` R-001 is open against it.

**The clock is New York's, not UTC's.** `[MEASURED]` over the window: the weekly close
lands at 20:00 UTC on 364 weeks and 21:00 UTC on 184, the split following New York's DST
calendar exactly. Payrolls: 125 releases, tick-volume peak at 08:00 New York on 47 of
them, and the mode moves with a deliberate one-hour shift.

**Costs are not calibratable on this feed.** Genuine bid/ask ticks begin 2026-03-02,
~0.40 years against 10.87 years of usable bars. The `spread` field on H1 bars is a
close-time quote, not a payable spread, and its coverage steps from 0.0% before 2016 to
95.7–99.8% after. H-005 registers the deviation and the substitute: a 75-point constant
floor, 5× the observed demo quote, with §10's event multiplier on top.

---

## 2. What the three features demonstrably do not contain

The feature set is `log_return_24`, `realized_vol_24`, `range_position_48`, combined by a
hand-rolled logistic regression — four parameters — over walk-forward folds with purge and
embargo.

**Finding: they carry no directional information at `H = 24` on this feed.**

Two independent measurements say so, and they fail in different ways, which is why both
are cited:

### 2.1 Probability quality, on true labels

H-001's unshuffled control, run alongside the shuffled-labels gate on the same folds:

> **BSS = −0.006766**, n = 1,364.

Against a shuffled-label null of mean −0.000855 across 30 seeds. **Fitting real labels
costs roughly eight times more out-of-sample skill than fitting noise does.** A model with
negative Brier skill is worse than climatology at assigning probabilities.

That alone is not decisive — a badly calibrated probability can still have an informative
sign — which is why the second measurement exists.

### 2.2 Direction, against the baseline that isolates the confound

H-003 measured the signal beating random entry by **+0.060398 R** per decision,
`p = 0.0204`, zero of thirty control arms doing as well. It also measured the signal going
long **767 times and short 597 — 56.2% long** — against a control that is 50% long by
construction, on an instrument with a secular uptrend across the window.

H-007 ran rung 2 on the same 1,364 decisions with the same geometry:

| arm | expectancy R | long % |
|---|---|---|
| signal | −0.096292 | 56.2% |
| always-long | −0.096150 | 100% |

> Difference **−0.000141 R**, one-sided `p = 0.5041`. Sensitivity 0.4942 and 0.5053 at
> block 1 and 25.

**The entire H-003 difference is attributable to long bias.** Worse than the net figure
shows: always-long paid 0.000727 R more per decision in costs, so gross the signal is
**behind by 0.000868 R**. The arm that took no view at all, and paid more to do it,
finished ahead.

Per fold the sign flips — signal ahead in folds 0 and 1, behind in 2, 3 and 4 — so the
pooled figure is two opposite regimes cancelling rather than a small stable effect.

**Consequence, recorded:** H-003's directional reading is withdrawn. Its run stands as a
record and its arithmetic holds; the inference does not. Under BH at `N_claims = 3` with
H-007 at `p = 0.5041`, nothing in the family clears §9.

### 2.3 What this does *not* establish

- Not that gold is unpredictable at `H = 24`. Three features and four parameters is a
  very small hypothesis class.
- Not that the features are worthless. `realized_vol_24` and `atr_14` may well carry
  *volatility* information; nothing here tested that, because the registered label is
  directional.
- Not that a different horizon behaves the same way. `H = 24` was registered before any
  run precisely so it could not be shopped, and it has never been varied.

---

## 3. Gates: which fired, which stayed silent, which are known blind

### Fired

Nothing tripped a kill criterion. **The ladder halted at a rung that has no K-code** —
`EVALUATION.md` §2 rung 2 is a baseline condition, not a §1 criterion, and K-4 covers rung
1 only, which H-003 passed. That is worth stating plainly: the thing that stopped this
project was not one of the eight things written down as able to stop it.

### Ran and stayed silent, correctly

| gate | status | measured |
|---|---|---|
| K-1 shuffled labels | did not trip | mean BSS −0.000855, CI upper −0.000577, max +0.000757, median −0.000734 across 30 seeds |
| K-2 causal test | standing, every commit | 4 features, all confirmation lags 0, leaky fixture rejected 3/3 |
| K-5 cost doubling | did not trip, twice | H-003 +0.067853 `p`=0.0078; H-007 +0.010961 `p`=0.3853 |
| K-6 decision floor | cleared 9.1× | 1,364 against 150, and label-free so known before each run |

### Never evaluated

- **K-3** (BSS on sealed holdout) — the holdout has never been opened. 0 of 3 uses spent.
- **K-7** (Deflated Sharpe) — DSR is not built. No claim so far reported a Sharpe.
- **K-8** (live vs backtest calibration) — nothing has run live.

### Known blind, measured rather than assumed

**K-1 cannot see two of the four leak modes at this combiner's capacity.** `[MEASURED]` at
4 parameters:

| leak mode | mean BSS | trips? |
|---|---|---|
| `label_in_features` | +0.999984 | yes |
| `target_encoding_on_all` | +0.247319 | yes |
| `train_test_overlap` | −0.000901 | **no** |
| `scaler_fit_on_all` | −0.001390 | **no** |

Train/test overlap is a genuine, serious leak that this gate does not detect — four
parameters cannot memorise 273 test rows folded into tens of thousands. Detectability is a
property of the estimator, not of the leak, and **it will change the day the combiner
does.** A higher-capacity stacker would trip it immediately, which means the K-1 result
does not transfer to a bigger model without being re-measured.

**Other known-dark areas:**

- The cost model's event set reaches **2.83% of bars** — 1,728 weekly-open, 125
  payrolls-hour. Every other scheduled release is priced at the flat floor. That error is
  *optimistic*, bounded by K-5 and the breakeven spread and removed by neither.
- **H-005 open.** No result may be described as satisfying §10. Everything so far is
  `RESEARCH.md` Tier 2 at best.
- **R-001 open.** The era boundaries have never been checked against FxPro's own
  announcements. Re-deriving them from the feed is circular and is refused at the point
  someone would reach for it.
- **No economic calendar.** Nothing in the repository knows when CPI, FOMC or ECB land.

---

## 4. Instrument defects found and fixed, in order

**Every one of these produced a fluent, internally consistent, wrong answer before it was
caught.** That is the pattern, and it is the most transferable thing this project has
learned. None of them announced itself; each was found by testing the instrument against
something outside itself.

### 4.1 The gap census: 223 → 73 → 7 → 2

Three fixes to `scripts/mt5_probe.py`, against **unchanged broker history**. Only the
instrument changed.

| count | defect in the instrument | after |
|---|---|---|
| **223** | Daily breaks classified by a single modal hour. The server clock puts the break an hour earlier in weeks when New York has changed over and Europe has not, so every break in those weeks was refiled as a hole — ~150 false defects, all in March and late October, exactly where someone hunting a DST artefact would find them and believe them. | **73** |
| **73** | No notion of an early close. A session that ends early and resumes on schedule is a closure; the census saw "a multi-bar gap inside a session" and called it a defect. All of them were US market holidays. | **7** |
| **7** | No independent reference. Five of the seven sit on the day after Christmas or New Year, visible immediately against the published CME/COMEX calendar, which the instrument did not consult. | **2** |

A 99% reduction in "candidate data defects" with no change to the data. Nothing in the
first report announced that 223 was a number about the instrument.

The same instrument also reported **"TRACKS DST — US RULE" from a bucket split 95 to 94**
— a four-week margin on a coin toss — and its own residual check confirmed the verdict,
because that check measured deviation from the very mode that was arbitrary. A second
anchor broke the tie; more data would not have.

### 4.2 The circular payrolls test

The natural form: resolve 08:30 New York to a UTC instant, look up the bar there, assert
it is the 08:00 New York bar. **The lookup key is the answer.** It holds for any conversion
whatsoever — shift the series an hour and a different bar moves into the slot and passes
just as happily.

It was written that way here first, **and it passed on data deliberately shifted by an
hour**. The replacement reads tick counts instead of labels and asks which hour is
unusually busy on payrolls Fridays, normalised against ordinary Fridays. The spike is in
the market, so it does not move when the labelling does.

### 4.3 Three UTC invariants that would have selected for the bug

The obvious statements — "the weekly boundaries are constant in UTC", "NFP is at 13:30
UTC" — are false on correctly converted data and true on data wrongly forced to a fixed
offset. **They would have failed on correct data and passed on the bug.**

`[MEASURED]`: the weekly close occupies two UTC hours, 20:00 on 364 weeks and 21:00 on
184. "NFP at 13:30 UTC" holds for 45 of 125 releases and fails for 80.

The invariants are now stated in the frame where the quantity is actually constant — New
York — with the UTC consequence stated in the form that is genuinely true. And they are
checked against `zoneinfo`'s IANA database rather than a DST rule re-derived in the same
file, because two copies of the same mistake agree.

A fourth finding came out of measuring what each check catches, by mutating the real
export four ways: **the release-hour check catches nothing at all.** Not merely less than
claimed — nothing. It is retained as a data-completeness check, renamed and re-documented,
because presenting it as a conversion invariant would have put a fourth green tick beside
a check that cannot go red.

### 4.4 The threshold that caught by luck

`MIN_PEAK_SHARE = 0.30` caught a US-DST-rule mutation at a measured 0.280. It looked like
the gate working. It was not: that mutation puts the volume peak in the *right* hour, so
the threshold fired for a reason nobody could state. Lowered to 0.25 — which does **not**
catch that mutation — and the reasoning written into `REPRODUCIBILITY.md` §10 as a rule:
**a gate that passes, or fires, for a reason nobody can state is not a working gate.**

### 4.5 The breakeven solver's false precision

Found during H-007. `solve_breakeven_spread` bisected a curve it had not checked for
monotonicity, and reported **"1,076.2 points, bracketed to within 3.9"** for a quantity
that crosses zero three times across the bracket:

```
0:+0.00055  250:+0.01947  500:-0.00400  750:-0.00608  1000:+0.00279
1250:-0.01644  1500:-0.01051  1750:-0.01297  2000:-0.00348
```

A real crossing, a meaningless number, and a tolerance that made it look precise. The
solver now probes a nine-point grid first and refuses when the sign changes more than
once, with the samples in the message so a reader sees the oscillation rather than taking
the refusal on trust.

It changed no verdict. It is recorded because an instrument that manufactures false
precision is a defect whether or not it changed a conclusion that time.

### 4.6 What the five have in common

- Each was **fluent**. None emitted a warning, a NaN, or a stack trace.
- Each was **internally consistent**. Three of the five had a self-check that agreed with
  them, because the self-check shared the assumption.
- Each was caught by **an external reference or an adversarial fixture**, never by
  re-reading the code: a second anchor, a published calendar, a deliberately corrupted
  input, a probe grid.
- Three of the five would have made the data look *worse* than it is, not better. The
  failure mode is not optimism; it is confidence.

---

## 5. What is registered and cannot now be quietly changed

Every constant below is pinned in `HYPOTHESES.md` before the run it governed. Changing any
of them requires a new hypothesis ID and a fresh draw against `N_claims`; changing one
after seeing a result it killed is hypothesis laundering under `RESEARCH.md` §5.2
regardless of the reasoning attached.

| constant | value | registered in |
|---|---|---|
| label horizon `H` | 24 bars | H-001 |
| `window_start` | 2015-09-11 | H-006 |
| `FIRST_TEST_FRACTION` | 0.50 | H-001, amended before the run |
| folds / decision spacing | 5 / 24 bars | H-001 |
| materiality floor ε | 0.01 | H-001 |
| spread floor | **75 points**, raisable only | H-005 |
| stop = target | 1.5 × ATR(14) | H-003 §D |
| max hold | 24 bars | H-003 §D |
| signal threshold τ | 0.0 | H-003 §B |
| bootstrap block | 10, sensitivity at 1 and 25 | H-003 §F |
| bootstrap | 10,000 resamples, seed 1337 | H-003 §F |
| cost divergence tolerance | 10% | H-003 §K |
| H-008 sweep | **0.75, 1.0, 1.5, 2.0, 3.0** | H-008, fixed before running |
| seeds | `shuffled_labels` 0–29, `random_entry` 0–29, `bootstrap` 1337 | `REPRODUCIBILITY.md` §3 |

**Thirteen cost and geometry constants, of which nine are judgement calls** (H-003 §L).
Seven of the nine are cost constants, and H-003 *measured* that its verdict did not turn on
them: cost divergence 0.000030 R against a 0.060398 R effect. The two that were never
measured are the 1.5× ATR geometry — which H-008 exists to sweep and has not — and the
bootstrap block, which was measured across its own registered range.

**Registered and unused.** H-008's five sweep values are fixed and the gate is unrun: its
own Order clause makes it conditional on H-007 passing, and a robustness sweep of a
retracted reading measures nothing. The values stay fixed for whenever there is a reading
to test.

**One thing the registry did that is worth recording on its own.** Registering H-007 moved
`N_claims` from 2 to 3, which moved the Benjamini–Hochberg rank-1 critical value from 0.025
to 0.0167 and stopped H-003's `p = 0.0204` clearing on its own — **before H-007 ran**. The
contingency (H-003 survives iff H-007 returns `p ≤ 0.0333`) was written down in advance and
resolved against. Registering a new claim weakened an accepted one, visibly, at the moment
of registration. That is the correction doing exactly what it is for.

---

## 6. Counters at the close of this phase

```
Registered ......... 8      Accepted 2 (H-001, H-003 — reading withdrawn)
                            Rejected 1 (H-007)
                            Standing 1 (H-002)
                            In flight 4
N_claims ........... 3      H-003, H-004, H-007
Holdout ............ 0 / 3 openings used
Runs ............... 3 evaluation manifests, all on clean trees
```

Build Order steps 1–6 are complete. Step 7 — the first agent — is **not** licensed: the
ladder halted at rung 2, and `EVALUATION.md` §2 makes rungs 3–5 meaningless until it is
passed.
