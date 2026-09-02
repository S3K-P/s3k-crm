"""What a deal must have before it may enter a stage.

This is the analysis's "Blueprint slot" (§5.6), sized for S3K: declarative
stage-entry requirements, not a workflow designer.

The value Zoho's Blueprint provides is *gating the change before it happens* —
a workflow rule reacts to a stage move that already occurred, which is too late
to prevent a deal reaching Proposal with no value on it. The cost of Blueprint
is a state-machine editor, a transition-owner model and a condition language.
S3K takes the first without the second: a column on the stage row listing the
fields that stage requires.

**Empty by default, on every stage.** The first draft of this derived
requirements from a stage's probability — anything past 25% needs a deal value,
past 50% needs a contact — and it was wrong in a way worth recording. It is a
defensible *policy*, but imposing it on every organization out of the box
means a product that silently started refusing stage moves people had been
making for months. Which fields a stage requires is a decision a sales manager
owns, exactly like ``follow_up_task_title`` next to it; the product's job is to
enforce what they configure, not to have opinions they did not ask for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.products.crm.opportunities.models import Opportunity, PipelineStage

#: Fields a stage may require, and how to name them to a user.
#:
#: A closed allow-list rather than "any column": a requirement naming a field
#: that does not exist would block every transition into that stage with a
#: message nobody could act on, and a typo in configuration should be caught
#: when it is saved rather than discovered by a rep who cannot move a deal.
GATEABLE_FIELDS: dict[str, str] = {
    "deal_value": "a deal value",
    "primary_contact_id": "a primary contact",
    "expected_close_date": "an expected close date",
    "forecast_category": "a forecast category",
    "competitor": "the competitor",
    "products": "the products involved",
    "notes": "notes",
}


@dataclass(frozen=True, slots=True)
class StageRequirement:
    """What is missing, and what to tell the user."""

    fields: tuple[str, ...]

    @property
    def is_satisfied(self) -> bool:
        return not self.fields

    def message(self, stage_name: str) -> str:
        readable = [GATEABLE_FIELDS.get(name, name) for name in self.fields]
        listed = (
            readable[0]
            if len(readable) == 1
            else f"{', '.join(readable[:-1])} and {readable[-1]}"
        )
        return f"Moving to “{stage_name}” needs {listed}."


def required_fields_for(stage: PipelineStage) -> tuple[str, ...]:
    """Which fields entering this stage requires.

    Terminal stages are exempt whatever they are configured with: closing a
    deal as lost must never be blocked by a missing deal value, because the
    reason it is lost may be that there never was one. A process that makes it
    hard to record bad news gets bad news recorded late, or not at all.
    """
    if stage.is_won or stage.is_lost:
        return ()
    configured = stage.required_fields or []
    return tuple(name for name in configured if name in GATEABLE_FIELDS)


def check_stage_entry(
    opportunity: Opportunity, stage: PipelineStage
) -> StageRequirement:
    """What ``opportunity`` still lacks to enter ``stage``."""
    missing = tuple(
        name
        for name in required_fields_for(stage)
        if _is_blank(getattr(opportunity, name, None))
    )
    return StageRequirement(fields=missing)


def describe(stage: PipelineStage) -> Sequence[str]:
    """A stage's requirements in plain words, for the UI.

    Telling somebody what a stage needs *before* they drag a card onto it is
    the difference between a helpful process and an obstructive one.
    """
    return [GATEABLE_FIELDS[name] for name in required_fields_for(stage)]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


__all__ = [
    "GATEABLE_FIELDS",
    "StageRequirement",
    "check_stage_entry",
    "describe",
    "required_fields_for",
]
