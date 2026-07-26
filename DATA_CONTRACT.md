# DATA_CONTRACT.md — Temporal Rules

**Every feature is bound by this contract. Violations trip K-2 and halt the pipeline.**
**Version:** 1.0

---

## 1. The Causality Rule

> **A feature computed at bar `T` may use only information that was observable at or before
> the close of bar `T`, in the timezone and with the publication lag that applied in real
> time.**

This sounds obvious. It is violated constantly, silently, and in ways that make backtests
look brilliant.

### Enforcement

`tests/test_causality.py` recomputes every feature on history truncated at `T` and asserts
bit-identical equality with the full-history value at `T`. Runs on every commit. No
exceptions, no skips, no `xfail`.

---

## 2. Confirmation Lag Registry

Structural features are **not knowable at the bar where they are later drawn**. Each must
declare its confirmation lag, and the pipeline must respect it.

| Feature | Defined at | Actually knowable at | Lag |
|---|---|---|---|
| Swing high/low (n-bar fractal) | bar `T` | bar `T + n` | `n` bars |
| Break of structure (BOS) | break bar | close of break bar | 0 (if close-confirmed) |
| Change of character (CHoCH) | requires prior swing | prior swing confirmation + break | `n` bars |
| Fair value gap (FVG) | 3-bar pattern | close of bar 3 | 2 bars |
| Order block | requires subsequent displacement | displacement confirmation | variable — **must be explicit** |
| Equal highs/lows | tolerance cluster | second touch close | 0 |
| Liquidity sweep | wick beyond level + reversal | reversal confirmation | ≥ 1 bar |
| ATR(n) | bar `T` | bar `T` | 0 |
| Session label | bar `T` | bar `T` | 0 |

> **The order block is the most common silent leak.** It is typically drawn retroactively
> once displacement is visible. If the pipeline marks it at the original candle without
> the displacement lag, every backtest using it is invalid — and will look excellent.

Any feature not in this table is prohibited until it is added with a declared lag.

---

## 3. Data Vintages and Revisions

Economic data is revised. Databases serve the **current** revision, not the value that was
known at the time.

| Source | Revision risk | Required handling |
|---|---|---|
| FRED macro series | High | Use ALFRED vintage series, or treat as Tier 3 evidence and document. |
| Economic calendar actuals | Medium | Store the first print alongside the revised value. Use the first print. |
| Broker OHLCV | Low | Pin the source. Different brokers differ in gold quotes. |
| VIX, DXY | Low | Note close-time alignment vs. gold's 23/5 session. |

Using revised macro data in a backtest is leakage. It is also easy to miss because the
numbers look correct.

---

## 4. Timestamp Discipline

- **All storage in UTC.** No exceptions. No local time anywhere in the data layer.
- Session boundaries defined in UTC with explicit DST handling:
  - Asia, London, New York — boundaries shift with DST and must be computed per-date, not
    hard-coded.
- **Bar timestamp convention: open-time.** Documented, enforced, tested. Mixing open-time
  and close-time conventions across sources is a leak of exactly one bar, and one bar is
  enough.
- Weekly rollover and the Sunday gap are explicit events, not smoothed over.

---

## 5. LLM Knowledge-Cutoff Contamination

**This risk is specific to LLM-based systems and has no analogue in classical quant.**

The pinned model has read commentary, retrospectives, and analysis covering historical
periods. It will not recall specific candles, but it carries a **directional prior** about
what happened. Backtesting on pre-cutoff data therefore measures the model's memory of the
narrative as much as its reasoning — and the results will look excellent.

### Mitigation, in order of strength

**A. Post-cutoff data only.** Strongest, and severely sample-limited. Track available
post-cutoff sample size explicitly; it will usually be below the K-6 threshold on its own.

**B. Anonymisation protocol.** Required for all pre-cutoff evaluation:
- Strip all dates and timestamps from anything reaching the LLM.
- Strip the instrument name. The panel sees "Instrument A", never "gold" or "XAUUSD".
- Convert prices to z-scores or percentage moves relative to a rolling window. Never
  absolute price levels — `2,070` is a date stamp.
- Strip news *content*; pass only event type and surprise magnitude in standard deviations.
- Randomise the presentation order of correlated instruments.

**C. Declaration.** Every evaluation report states which protocol was used. Pre-cutoff
results without protocol B are **Tier 3 evidence only** and cannot support acceptance of
any hypothesis.

> Deterministic features are unaffected by this. This is another argument for keeping the
> LLM out of the decision path: the deterministic layer can be validated on decades of
> history, while the LLM layer effectively cannot.

---

## 6. Missing Data

| Situation | Policy |
|---|---|
| Missing bar | Forward-fill **prohibited** in features. Mark bar invalid; exclude decisions. |
| Missing macro series | Feature returns `None`. Agents receiving `None` must emit `no_signal`, never impute. |
| Feed disagreement | Log both. Halt if divergence exceeds tolerance. |
| Late news release | Timestamped at actual receipt, not scheduled time. |

**Silent imputation is prohibited everywhere.** A `None` that propagates loudly is safe. A
forward-filled value that looks plausible is not.

---

## 7. Feature Declaration Format

Every feature ships with this block, or it does not enter the pipeline.

```yaml
name: liquidity_sweep_high
version: 1
inputs: [ohlcv_m15, equal_highs_level]
lookback_bars: 96
confirmation_lag_bars: 1
timezone: UTC
returns: {type: float, range: [0.0, 1.0], null_allowed: true}
null_semantics: "insufficient history or no level within tolerance"
causal_test: tests/features/test_liquidity_sweep_high.py
revision_risk: none
notes: "Level must be confirmed before the sweep bar. Do not use levels formed after T."
```

---

## 8. Snapshot Immutability

- Every evaluation runs against a **versioned, content-hashed data snapshot**.
- Snapshots are immutable. Corrections create a new version; they never modify the old one.
- The run manifest records the snapshot hash. A result whose snapshot no longer exists is
  unreproducible and is void.
