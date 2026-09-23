"""The CRM's currency — the one place it is decided.

New opportunities default to :data:`CRM_CURRENCY`, and every money figure the
backend writes into prose (AI context, prioritization reasons, notifications)
goes through :func:`format_money`, so the product speaks one currency.

Display only: stored amounts are never converted. A deal saved as ``50000``
reads as ``₹50,000`` whatever code its ``currency`` column holds. The frontend
twin of this module is ``frontend/lib/currency.ts``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

CRM_CURRENCY: Final = "INR"
CRM_CURRENCY_SYMBOL: Final = "₹"


def _group_indian(digits: str) -> str:
    """``12500000`` → ``1,25,00,000``: last three digits, then pairs."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs) + "," + tail


def format_money(amount: Decimal | int | float, *, decimals: int = 0) -> str:
    """``₹12,50,000`` — Indian digit grouping, rounded to ``decimals`` places."""
    rendered = f"{abs(Decimal(amount)):.{decimals}f}"
    whole, _, fraction = rendered.partition(".")
    sign = "-" if Decimal(amount) < 0 and Decimal(rendered) != 0 else ""
    text = f"{sign}{CRM_CURRENCY_SYMBOL}{_group_indian(whole)}"
    return f"{text}.{fraction}" if fraction else text


__all__ = ["CRM_CURRENCY", "CRM_CURRENCY_SYMBOL", "format_money"]
