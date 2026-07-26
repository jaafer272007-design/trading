"""Label layer.

Labels look forward by construction — they are the outcome being predicted.
They are deliberately kept out of ``src/features/`` so they can never enter
the causal sweep, which would (correctly) reject them.
"""
