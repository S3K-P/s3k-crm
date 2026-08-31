"""What the provider does with a response, without calling one.

The interesting logic in ``app.platform.ai.provider`` is not the HTTP call —
it is what gets believed about the response afterwards. These tests pin the
two properties the feature's honesty rests on:

* a source exists only because a ``web_search_tool_result`` block reported it;
* a soft server-tool failure (HTTP 200, error object instead of a result list)
  degrades to partial results rather than crashing.

``harvest_blocks`` is deliberately a module-level function over duck-typed
blocks, so the fixtures below are plain objects rather than SDK models and no
client, key or network is involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.ai.provider import harvest_blocks


def text_block(text: str, citations: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text, citations=citations)


def citation(url: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="web_search_result_location", url=url, title="t", cited_text="c"
    )


def search_result(url: str, title: str = "Result", page_age: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        type="web_search_result", url=url, title=title, page_age=page_age
    )


def search_results_block(results: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(type="web_search_tool_result", content=results)


def search_error_block(code: str) -> SimpleNamespace:
    """A failed search. Note ``content`` is an object, not a list."""
    return SimpleNamespace(
        type="web_search_tool_result", content=SimpleNamespace(error_code=code)
    )


def test_text_blocks_are_concatenated_in_order() -> None:
    texts, _sources, _cited, _searches = harvest_blocks(
        [text_block("## Overview"), text_block("Second part.")]
    )

    assert texts == ["## Overview", "Second part."]


def test_a_source_is_recorded_only_when_the_tool_returned_it() -> None:
    """The anti-fabrication property, stated as a test.

    The prose names a URL the search tool never returned. It must not become a
    source: the panel is evidence, and evidence comes from the tool.
    """
    _texts, sources, _cited, _searches = harvest_blocks(
        [
            text_block("According to https://invented.example/report, revenue doubled."),
            search_results_block([search_result("https://real.example/filing")]),
        ]
    )

    assert [source.url for source in sources] == ["https://real.example/filing"]


def test_page_age_and_title_are_carried_through_verbatim() -> None:
    _texts, sources, _cited, _searches = harvest_blocks(
        [
            search_results_block(
                [search_result("https://a.example", title="A Filing", page_age="2 days ago")]
            )
        ]
    )

    assert sources[0].title == "A Filing"
    assert sources[0].page_age == "2 days ago"


def test_a_url_with_no_title_falls_back_to_the_url() -> None:
    _texts, sources, _cited, _searches = harvest_blocks(
        [search_results_block([search_result("https://a.example", title="")])]
    )

    assert sources[0].title == "https://a.example"


def test_a_result_without_a_url_is_dropped() -> None:
    """A source with no URL cannot be checked, so it is not a source."""
    _texts, sources, _cited, _searches = harvest_blocks(
        [search_results_block([SimpleNamespace(type="web_search_result", url=None, title="x")])]
    )

    assert sources == []


def test_citations_mark_which_sources_were_actually_quoted() -> None:
    _texts, _sources, cited, _searches = harvest_blocks(
        [
            text_block("Revenue doubled.", citations=[citation("https://a.example")]),
            search_results_block(
                [search_result("https://a.example"), search_result("https://b.example")]
            ),
        ]
    )

    assert cited == {"https://a.example"}


def test_a_non_web_citation_type_is_ignored() -> None:
    """Only web-search citations mark a *page* as cited."""
    _texts, _sources, cited, _searches = harvest_blocks(
        [
            text_block(
                "From the attachment.",
                citations=[SimpleNamespace(type="char_location", url="https://a.example")],
            )
        ]
    )

    assert cited == set()


def test_a_search_error_block_does_not_raise_and_keeps_earlier_results() -> None:
    """Partial source availability is a supported outcome, not a failure.

    The error block's ``content`` is an object rather than a list. Indexing it
    is the documented way to turn a soft failure into a crash, so this test
    exists to keep the branch that checks for it.
    """
    texts, sources, _cited, _searches = harvest_blocks(
        [
            search_results_block([search_result("https://a.example")]),
            search_error_block("max_uses_exceeded"),
            text_block("Partial answer."),
        ]
    )

    assert [source.url for source in sources] == ["https://a.example"]
    assert texts == ["Partial answer."]


def test_search_invocations_are_counted() -> None:
    _texts, _sources, _cited, searches = harvest_blocks(
        [
            SimpleNamespace(type="server_tool_use", name="web_search"),
            SimpleNamespace(type="server_tool_use", name="web_search"),
            SimpleNamespace(type="server_tool_use", name="code_execution"),
        ]
    )

    assert searches == 2


def test_unknown_block_types_are_skipped_rather_than_failing() -> None:
    """A block type added by a future API version must not break a report."""
    texts, sources, cited, searches = harvest_blocks(
        [SimpleNamespace(type="something_new"), text_block("Fine.")]
    )

    assert texts == ["Fine."]
    assert (sources, cited, searches) == ([], set(), 0)
