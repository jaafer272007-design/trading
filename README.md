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

## Status

This repository is research infrastructure: a data layer, a feature layer with
causal tests, and — as later phases land — a backtest engine and evaluation
harness. It is not trading advice, and nothing in this repository is a claim
that any strategy, feature, or model has an edge. Per `RESEARCH.md` §0, the
project's default position is that it has no edge, and every result is
presumed to be noise, leakage, or overfitting until it survives the full
protocol in `EVALUATION.md`.
