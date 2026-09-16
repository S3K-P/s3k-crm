"""Turning one model turn into a validated Pydantic object.

Every Checkpoint 7 feature that asks the model for something other than free
prose (account intelligence, next-best-action, meeting extraction, a
natural-language query translation, an email draft) goes through
:func:`run_structured`. It is the one place that:

* calls the gateway with ``web_search=False`` — none of these features need
  the web, and asking for it would let the model wander off real CRM data
  (§23, bounded context);
* strips the Markdown code fence a model commonly wraps JSON in;
* parses the result as JSON and validates it against the caller's Pydantic
  schema, so a malformed or unexpected shape is rejected *before* it reaches
  any caller (§19, §20) — never treated as executable instructions, never
  partially trusted;
* raises a typed, stable error on failure rather than letting a ``KeyError``
  or a Pydantic ``ValidationError`` escape as a 500.

Nothing here decides *what* to ask — that is each feature's own prompt in
``prompts.py``. This module only knows how to get a promised shape back out.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import status
from pydantic import BaseModel, ValidationError

from app.core.exceptions import AppError
from app.platform.ai.provider import ResearchResult
from app.platform.ai.service import AiGatewayService

#: A model asked for JSON commonly still wraps it in a fenced code block.
#: Stripped rather than relied upon: the prompt also asks for bare JSON, and
#: this is a tolerance for what models actually do, not the contract.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class AiInvalidOutputError(AppError):
    """The model's answer could not be parsed as the shape this feature needs.

    A 502, like :class:`~app.platform.ai.provider.AiProviderError`: the
    provider was reachable and answered, but not usefully — the caller's fix
    is to retry, not to reconfigure anything.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ai_invalid_output"
    message = "The AI returned an answer that could not be understood. Please try again."


def extract_json(text: str) -> Any:
    """Best-effort extraction of one JSON value from a model's answer.

    Raises:
        AiInvalidOutputError: no JSON object could be parsed at all.
    """
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Last resort: a model that added a sentence before/after the object.
    # Bounded to the outermost braces only — never a regex that reconstructs
    # or repairs JSON, which would risk accepting something the model did not
    # actually produce.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise AiInvalidOutputError


def parse_structured[SchemaT: BaseModel](text: str, schema: type[SchemaT]) -> SchemaT:
    """Parse and validate one model answer against ``schema``.

    Raises:
        AiInvalidOutputError: the answer is not valid JSON, or does not match
            ``schema`` — an unknown field, a missing required one, or a value
            outside its declared enum/bounds. Nothing partially validated is
            ever returned; the caller gets a clean failure to retry.
    """
    raw = extract_json(text)
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise AiInvalidOutputError from exc


async def run_structured[SchemaT: BaseModel](
    gateway: AiGatewayService,
    schema: type[SchemaT],
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    system: str,
    messages: Sequence[dict[str, Any]],
    feature: str,
) -> tuple[SchemaT, ResearchResult]:
    """Run one non-research turn and validate its answer against ``schema``.

    ``web_search=False``: every structured feature here reasons over CRM
    context already assembled by the caller, never over the live web — see
    the module docstring.
    """
    result = await gateway.run_turn(
        organization_id=organization_id,
        actor_id=actor_id,
        system=system,
        messages=messages,
        feature=feature,
        web_search=False,
    )
    return parse_structured(result.text, schema), result


__all__ = [
    "AiInvalidOutputError",
    "extract_json",
    "parse_structured",
    "run_structured",
]
