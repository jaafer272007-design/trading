"""Layer 1 — the risk and cost layer. Deterministic accounting on live state.

.. important::

   **This package joins no pipeline and makes no claim about markets.**

   Nothing here is a hypothesis, nothing here draws on ``N_claims``, and no
   result produced by this package may be cited as evidence for or against
   anything in ``HYPOTHESES.md``. It predicts nothing. It observes an account
   and does arithmetic on what it observes.

   The dependency runs one way and only one way: ``risk`` imports two
   constants from ``backtest.costs`` in order to *compare against them*, and
   nothing under ``src/backtest``, ``src/evaluation``, ``src/features`` or
   ``src/models`` imports anything from here. ``tests/risk/test_scope.py``
   asserts that, so the boundary is a build failure rather than an intention.

Why this layer exists, and why it is first
------------------------------------------

The build order in ``CLAUDE.md`` puts infrastructure before agents. This layer
sits before even that, because the two mechanisms that actually emptied the
account it is being written for are not prediction problems:

1. A drawdown, with nothing arithmetic standing between the account and it.
2. A long position held for two months, whose financing cost consumed what the
   drawdown left.

Neither needs a signal to address and neither is addressed by having one. Both
are visible in account state that the terminal already publishes, and both
reduce to arithmetic that is either right or wrong — which is why this layer
needs tests but does not need a backtest.

What it does not do
-------------------

- It does not predict. No direction, no probability, no signal, no edge.
- It does not trade. ``order_send`` does not appear anywhere in this
  repository and must not, per ``RESEARCH.md`` §2. Every MT5 call the adapter
  makes is a read or a pure calculation.
- It does not say whether a trade is a good idea. It says what a trade costs
  to hold and what it does to the account if held.
- Its days-to-margin-call figure is arithmetic under an explicitly stated
  constant-price assumption. It is not a forecast and must never be read as
  one.

What it refuses to do
---------------------

Every broker-specific quantity that cannot be read unambiguously produces a
:class:`~risk.refusal.Refusal` naming what was missing, rather than a default.
An unrecognised swap mode, an unrecognised margin-call mode, an unmeasurable
server clock and an unusable tick value are all refusals. ``CLAUDE.md`` Hard
Rule 6 — missing data returns ``None`` and propagates loudly — is the rule
being applied, and this is the layer where a silent default would cost money
rather than a paper.
"""
