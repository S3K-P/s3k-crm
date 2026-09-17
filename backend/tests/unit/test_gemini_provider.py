"""What the Gemini provider believes about a response, without calling one.

The counterpart to ``test_ai_provider`` for the second vendor, pinning the same
honesty properties plus the one this provider introduces:

* a source exists only because ``grounding_chunks`` reported it;
* ``cited`` is set only where a ``grounding_support`` pointed at that chunk;
* an answer produced **without** the search tool is marked ungrounded, so the
  interface can say the report was written from memory rather than researched.

``harvest_grounding`` is a module-level function over duck-typed objects, so
the fixtures below are plain namespaces — no SDK models, no client, no key.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.ai.gemini import _to_contents, harvest_grounding


def chunk(uri: str | None, title: str | None = None, domain: str | None = None) -> Any:
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title, domain=domain))


def support(*indices: int) -> Any:
    return SimpleNamespace(grounding_chunk_indices=list(indices))


def candidate(chunks: list[Any] | None = None, supports: list[Any] | None = None) -> Any:
    if chunks is None and supports is None:
        return SimpleNamespace(grounding_metadata=None)
    return SimpleNamespace(
        grounding_metadata=SimpleNamespace(
            grounding_chunks=chunks or [], grounding_supports=supports or []
        )
    )


# --- Sources are observed, never invented -----------------------------------


def test_a_source_is_recorded_only_when_grounding_reported_it() -> None:
    sources, _ = harvest_grounding(
        candidate(chunks=[chunk("https://example.com/a", "Alpha")])
    )

    assert [(source.title, source.url) for source in sources] == [
        ("Alpha", "https://example.com/a")
    ]


def test_a_chunk_without_a_uri_is_dropped() -> None:
    """No URL means nothing a reader could check. It is not a source."""
    sources, _ = harvest_grounding(
        candidate(chunks=[chunk(None, "No link"), chunk("https://example.com/b")])
    )

    assert [source.url for source in sources] == ["https://example.com/b"]


def test_a_source_with_no_title_falls_back_to_domain_then_url() -> None:
    sources, _ = harvest_grounding(
        candidate(
            chunks=[
                chunk("https://example.com/a", None, "example.com"),
                chunk("https://example.com/b", None, None),
            ]
        )
    )

    assert [source.title for source in sources] == ["example.com", "https://example.com/b"]


def test_no_grounding_metadata_yields_no_sources_rather_than_raising() -> None:
    """Absent metadata is the normal shape when the model did not search."""
    sources, cited = harvest_grounding(candidate())

    assert sources == []
    assert cited == set()


# --- Citations distinguish retrieved from quoted ----------------------------


def test_supports_mark_which_sources_were_actually_used() -> None:
    sources, cited = harvest_grounding(
        candidate(
            chunks=[chunk("https://a.test"), chunk("https://b.test")],
            supports=[support(1)],
        )
    )

    assert {source.url for source in sources} == {"https://a.test", "https://b.test"}
    # Only the chunk a sentence rested on is a citation; the other was merely read.
    assert cited == {"https://b.test"}


def test_an_out_of_range_support_index_is_ignored() -> None:
    """The index comes from the provider; trusting it blindly would raise
    mid-report on a response that is otherwise perfectly usable."""
    sources, cited = harvest_grounding(
        candidate(chunks=[chunk("https://a.test")], supports=[support(0, 7, -1)])
    )

    assert cited == {"https://a.test"}
    assert len(sources) == 1


# --- Message translation ----------------------------------------------------


def test_the_assistant_role_is_translated_to_gemini_naming() -> None:
    """The gateway speaks one dialect; each provider translates its own."""
    contents = _to_contents(
        [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    )

    assert [content.role for content in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "hello"


def test_empty_and_non_string_turns_are_skipped() -> None:
    """A blank turn would be rejected by the API; dropping it is kinder than
    failing a research run over it."""
    contents = _to_contents(
        [
            {"role": "user", "content": "  "},
            {"role": "user", "content": None},
            {"role": "user", "content": "real"},
        ]
    )

    assert len(contents) == 1
    assert contents[0].parts[0].text == "real"


def test_an_unexpected_role_degrades_to_model_rather_than_raising() -> None:
    contents = _to_contents([{"role": "system", "content": "x"}])

    assert [content.role for content in contents] == ["model"]
