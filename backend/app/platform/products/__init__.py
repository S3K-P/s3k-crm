"""Shared Platform module: products and entitlements (ADR-011).

Answers *may this organization open this product at all*, which is the
question that sits in front of every permission check. See `policies.py` for
the gate and `service.py` for the rule it applies.
"""

from __future__ import annotations
