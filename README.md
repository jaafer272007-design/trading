# trading-research

A quant research platform for gold that extracts market state deterministically
and reproducibly, generates directional hypotheses with calibrated
probabilities, subjects every hypothesis to adversarial testing before it can
influence anything, and logs every decision with full provenance so it can be
audited a year later. It is explicitly not an autonomous system trading
unsupervised capital, not a predictor — it produces calibrated probabilities,
not forecasts — not a system whose edge is meant to derive from an LLM's
"market intuition," and not a backtest tuned to its own history: backtests here
are used to falsify hypotheses, not to fit them. See `RESEARCH.md` §1–2 for the
full statement.

## Read this first

`CLAUDE.md` requires these five documents be read, in this order, before any
code is written or changed:

1. `RESEARCH.md` — what counts as evidence, and what this project refuses to be
2. `DATA_CONTRACT.md` — temporal rules every feature must obey
3. `EVALUATION.md` — kill criteria and measurement protocol
4. `HYPOTHESES.md` — the pre-registration registry; what is currently in flight
5. `REPRODUCIBILITY.md` — pinning, seeds, manifests

They are the specification. Code that contradicts them is wrong even if it
runs.

## Setup

Requires Python 3.12 (pinned in `.python-version` and `pyproject.toml`) and
[uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

One-time, per clone:

```sh
git config core.hooksPath hooks
```

This points git at the version-controlled hooks in `hooks/` instead of the
default, gitignored `.git/hooks/`. Without it, `hooks/pre-push` is never run.

### Running the gates

`.github/workflows/ci.yml` is the authoritative gate and runs on every push and
pull request. To run the same checks locally:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict
uv run pytest
```

### Pre-push hook

Once `core.hooksPath` is set, `hooks/pre-push` runs automatically before every
`git push`. It refuses to run against a dirty working tree
(`REPRODUCIBILITY.md` §5), then runs the same four gates as CI, in the same
order, exiting non-zero on the first failure with the specific gate and rule
it enforces.

## Scripts in `scripts/`

Two of these are **instruments, not pipeline code**. They run on the Windows
machine that hosts the MetaTrader 5 terminal, import nothing from this
repository, and are excluded from `mypy`'s file set because nothing here can
import them either. They exist because the data layer's design depends on
facts about the broker's feed that cannot be looked up.

| Script | What it does | What it must never do |
|---|---|---|
| `mt5_probe.py` | Measures the feed: history depth, bar density by year, gap census, spread-field recording depth, and which DST rule the server clock follows. Prints a report and nothing else. | Write any file, ingest, export, or transform. Every number it prints is `[MEASURED]` or explicitly `[ESTIMATE]`. |
| `capture_ticks.py` | Records live bid/ask ticks, append-only, one file per server day with a hash-chain sidecar. Resumes after interruption and survives reboots under Task Scheduler. | Write inside a git repository — it checks and refuses. Nothing it produces enters the pipeline until ingested through the normal path. |
| `run_h001_harness_validation.py` | Runs the shuffled-labels harness against the leak-fixture suite and reports which modes trip. Pipeline code; this one is in the evaluation path. | — |

Neither instrument reads, stores, or prints credentials. Both attach to a
terminal that is already logged in, and the account login is masked in every
line they emit.

**Read the correction log at the top of `mt5_probe.py` before trusting any
number it prints.** Across three fixes to the instrument — against unchanged
broker history — its count of "candidate data defects" went 223 → 73 → 7 → 2,
and at every stage the output was fluent, internally consistent, and wrong.
It is the clearest evidence this project has that a measurement tool
manufactures findings until the tool itself is tested. Every classification
the script now makes is checked against something outside itself: a second
anchor, a published exchange calendar, or a reconciliation that must close to
zero — and it reports UNDETERMINED rather than choosing when those disagree.

`capture_ticks.py` exists to close **H-005**, which registers the project's
one live deviation from `EVALUATION.md` §10: the cost model's spread cannot be
calibrated, because genuine bid/ask history for this feed is ~0.4 years deep
against the 10.87 years of usable bars declared by **H-006**. Until that capture
matures, backtests run against a pessimistic constant floor and report a
breakeven spread beside every result. See `HYPOTHESES.md` §5.

The feed advertises 18.38 years. Only 10.87 of them carry more than one bar a
day, and H-006 registers that boundary so the shortfall is a declared decision
rather than a truncation discovered later in a run manifest.

## Status

This repository is research infrastructure: a data layer, a feature layer with
causal tests, and — as later phases land — a backtest engine and evaluation
harness. It is not trading advice, and nothing in this repository is a claim
that any strategy, feature, or model has an edge. Per `RESEARCH.md` §0, the
project's default position is that it has no edge, and every result is
presumed to be noise, leakage, or overfitting until it survives the full
protocol in `EVALUATION.md`.
