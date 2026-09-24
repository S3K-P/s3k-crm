"""The CRM display currency: INR, Indian digit grouping, amounts never converted."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.products.crm.currency import CRM_CURRENCY, format_money
from app.products.crm.opportunities.schemas import OpportunityCreate


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "₹0"),
        (999, "₹999"),
        (1000, "₹1,000"),
        (125000, "₹1,25,000"),
        (Decimal("12645000"), "₹1,26,45,000"),
        (Decimal("2500000.40"), "₹25,00,000"),
        (-50000, "-₹50,000"),
    ],
)
def test_format_money_uses_rupees_and_indian_grouping(amount: object, expected: str) -> None:
    assert format_money(amount) == expected  # type: ignore[arg-type]


def test_format_money_keeps_requested_decimals() -> None:
    assert format_money(Decimal("12500"), decimals=2) == "₹12,500.00"


def test_new_opportunities_default_to_the_crm_currency() -> None:
    assert CRM_CURRENCY == "INR"
    create = OpportunityCreate.model_validate(
        {
            "name": "Deal",
            "account_id": "00000000-0000-0000-0000-000000000001",
            "stage_id": "00000000-0000-0000-0000-000000000002",
        }
    )
    assert create.currency == "INR"
