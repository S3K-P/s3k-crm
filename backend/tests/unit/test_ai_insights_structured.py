"""Turning a model's free-text answer into a validated object (§19, §20).

No network, no database: ``extract_json``/``parse_structured`` are pure
functions over a string, which is exactly what makes a malformed or
adversarial model answer cheap to pin down here.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.products.crm.ai_insights.structured import (
    AiInvalidOutputError,
    extract_json,
    parse_structured,
)


class Greeting(BaseModel):
    model_config = {"extra": "forbid"}

    message: str


def test_bare_json_is_parsed() -> None:
    assert extract_json('{"message": "hi"}') == {"message": "hi"}


def test_a_markdown_fence_is_stripped() -> None:
    assert extract_json('```json\n{"message": "hi"}\n```') == {"message": "hi"}


def test_a_fence_with_no_language_tag_is_stripped() -> None:
    assert extract_json('```\n{"message": "hi"}\n```') == {"message": "hi"}


def test_a_sentence_wrapped_around_the_object_is_tolerated() -> None:
    """A model that adds a pleasantry before/after the JSON is still usable."""
    text = 'Sure, here you go:\n{"message": "hi"}\nHope that helps!'

    assert extract_json(text) == {"message": "hi"}


def test_unparseable_text_raises_the_typed_error() -> None:
    with pytest.raises(AiInvalidOutputError):
        extract_json("I cannot help with that.")


def test_broken_json_inside_braces_is_not_silently_repaired() -> None:
    """The bounded-brace fallback must not accept text that merely contains
    braces without being valid JSON — repairing it would mean accepting
    something the model did not actually produce.
    """
    with pytest.raises(AiInvalidOutputError):
        extract_json("{not valid json at all}")


def test_a_valid_shape_validates() -> None:
    result = parse_structured('{"message": "hi"}', Greeting)

    assert result.message == "hi"


def test_an_unexpected_field_is_rejected() -> None:
    """``extra=forbid`` on every structured schema: a model padding its answer
    with an extra field must fail loudly, not be silently ignored.
    """
    with pytest.raises(AiInvalidOutputError):
        parse_structured('{"message": "hi", "extra_field": "surprise"}', Greeting)


def test_a_missing_required_field_is_rejected() -> None:
    with pytest.raises(AiInvalidOutputError):
        parse_structured("{}", Greeting)


def test_malformed_json_never_reaches_the_caller_as_a_validation_error() -> None:
    """The caller only ever sees ``AiInvalidOutputError`` — never a raw
    ``json.JSONDecodeError`` or Pydantic ``ValidationError`` escaping as a 500.
    """
    with pytest.raises(AiInvalidOutputError):
        parse_structured("not json", Greeting)
