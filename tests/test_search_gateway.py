from __future__ import annotations

from datetime import date
import logging
from typing import cast

import pytest

from vanguard.research.search_gateway import (
    ExaSearchAdapter,
    SearchGateway,
    TavilySearchAdapter,
    count_domains,
    source_diversity_note,
    underrepresented_domains,
    _required_api_key,
)
from vanguard.research.defaults import default_search_gateway
from vanguard.research.search_gateway_models import (
    NormalizedSearchResult,
    SearchGatewayError,
    SearchPolicy,
)
from vanguard.utils.urls import (
    allowed_url_target_matches_url,
    normalize_allowed_url_target,
    normalize_domain,
    normalize_search_query,
    normalize_url_for_deduplication,
)


class RecordingClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.response


def test_search_policy_normalizes_optional_domains_and_dates():
    policy = SearchPolicy(
        allowed_domains=("https://www.Example.com/path", "example.com", "Docs.Example.com"),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert policy.allowed_domains == ("example.com", "docs.example.com")
    assert policy.start_date == date(2025, 1, 1)
    assert policy.end_date == date(2025, 12, 31)


def test_allowed_url_target_normalization_preserves_path_prefix():
    assert normalize_allowed_url_target("https://aws.amazon.com/blogs/aws") == normalize_allowed_url_target(
        "aws.amazon.com/blogs/aws/"
    )
    assert allowed_url_target_matches_url(
        normalize_allowed_url_target("aws.amazon.com/blogs/aws/"),
        "https://aws.amazon.com/blogs/aws/x",
    )
    assert not allowed_url_target_matches_url(
        normalize_allowed_url_target("aws.amazon.com/blogs/aws/"),
        "https://aws.amazon.com/blogs/physical-ai/x",
    )


def test_search_policy_allows_empty_constraints():
    policy = SearchPolicy()

    assert policy.allowed_domains == ()
    assert policy.start_date is None
    assert policy.end_date is None


def test_search_policy_rejects_reversed_date_window():
    with pytest.raises(SearchGatewayError, match="start_date"):
        SearchPolicy(start_date=date(2026, 1, 1), end_date=date(2025, 1, 1))


@pytest.mark.asyncio
async def test_exa_adapter_injects_only_present_policy_constraints():
    client = RecordingClient(
        {
            "results": [
                {
                    "url": "https://example.com/a?utm_source=x&id=1",
                    "title": "A",
                    "highlights": ["Relevant excerpt"],
                    "text": "Full Exa source text.",
                    "publishedDate": "2025-03-01",
                }
            ]
        }
    )
    adapter = ExaSearchAdapter(client=client, num_results=7, highlights_max_characters=750)

    results = await adapter.search(
        "query",
        SearchPolicy(allowed_domains=("example.com",), start_date=date(2025, 1, 1)),
        highlight_query="focused evidence",
    )

    assert client.calls == [
        (
            "query",
            {
                "type": "auto",
                "num_results": 7,
                "contents": {
                    "text": {"max_characters": 20_000},
                    "summary": {
                        "query": (
                            "Provide a concise, high-signal summary of the most relevant information. "
                            "Focus on facts, key developments, and useful insights."
                        )
                    },
                },
                "include_domains": ["example.com"],
                "start_published_date": "2025-01-01",
            },
        )
    ]
    assert results[0].provider == "exa"
    assert results[0].summary is None
    assert results[0].raw_content == "Full Exa source text."
    assert results[0].published_date == "2025-03-01"
    assert results[0].normalized_url == "https://example.com/a?id=1"


def test_exa_adapter_uses_compact_content_defaults():
    adapter = ExaSearchAdapter()

    assert adapter.num_results == 5
    assert adapter.text_max_characters == 20_000
    assert adapter._contents("focused question") == {
        "text": {"max_characters": 20_000},
        "summary": {
            "query": (
                "Provide a concise, high-signal summary of the most relevant information. "
                "Focus on facts, key developments, and useful insights."
            )
        },
    }


def test_exa_adapter_can_disable_full_text():
    adapter = ExaSearchAdapter(text_max_characters=None)

    assert adapter._contents("focused question") == {
        "summary": {
            "query": (
                "Provide a concise, high-signal summary of the most relevant information. "
                "Focus on facts, key developments, and useful insights."
            )
        },
    }


@pytest.mark.asyncio
async def test_tavily_adapter_uses_full_policy_domains_when_focus_is_provided():
    client = RecordingClient(
        {
            "results": [
                {
                    "url": "https://docs.example.com/post",
                    "title": "Post",
                    "content": "Snippet",
                    "raw_content": "# Full markdown\n\nLonger source text.",
                    "published_date": "2025-04-01",
                }
            ]
        }
    )
    adapter = TavilySearchAdapter(
        client=client,
        max_results=3,
        search_depth="advanced",
        include_raw_content="markdown",
    )

    results = await adapter.search(
        "query",
        SearchPolicy(
            allowed_domains=("example.com", "docs.example.com"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 5, 1),
        ),
        focused_domains=("docs.example.com",),
    )

    assert client.calls == [
        (
            "query",
            {
                "max_results": 3,
                "search_depth": "advanced",
                "include_raw_content": "markdown",
                "include_domains": ["docs.example.com"],
                "start_date": "2025-01-01",
                "end_date": "2025-05-01",
            },
        )
    ]
    assert results[0].provider == "tavily"
    assert results[0].summary == "Snippet"
    assert results[0].raw_content == "# Full markdown\n\nLonger source text."
    assert results[0].published_date == "2025-04-01"


def test_tavily_adapter_omits_raw_content_by_default():
    adapter = TavilySearchAdapter()

    assert adapter.include_raw_content is False


def test_default_search_gateway_configures_results_per_provider():
    gateway = default_search_gateway(results_per_provider=10)

    exa = cast(ExaSearchAdapter, gateway.providers[0])
    tavily = cast(TavilySearchAdapter, gateway.providers[1])
    assert exa.num_results == 10
    assert tavily.max_results == 10
    assert tavily.search_depth == "basic"
    assert tavily.include_raw_content == "markdown"


class FakeProvider:
    name = "fake"

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def search(self, query, policy, focused_domains=(), highlight_query=None):
        self.calls.append((query, policy, focused_domains, highlight_query))
        return self.results


class FailingProvider:
    def __init__(self, name="failing", error: Exception | None = None):
        self.name = name
        self.error = error or RuntimeError("provider unavailable")

    async def search(self, query, policy, focused_domains=(), highlight_query=None):
        raise self.error


@pytest.mark.asyncio
async def test_gateway_logs_provider_result_counts_without_result_metadata(caplog):
    gateway = SearchGateway(
        [
            FakeProvider(
                [
                    NormalizedSearchResult(
                        provider="exa",
                        query="q",
                        url="https://example.com/a",
                        title="A",
                        summary="Short summary",
                        raw_content="Full source text",
                        published_date="2026-05-19",
                    )
                ]
            )
        ]
    )

    with caplog.at_level(logging.INFO, logger="vanguard.research.search_gateway"):
        await gateway.search("q", SearchPolicy())

    assert "Search provider completed: provider=fake result_count=1" in caplog.text
    assert "https://example.com/a" not in caplog.text
    assert "canonical_domain" not in caplog.text
    assert "raw_content_characters" not in caplog.text
    assert "Full source text" not in caplog.text


@pytest.mark.asyncio
async def test_gateway_uses_focused_domains_for_provider_narrowing_but_filters_by_policy_allowlist():
    results = [
        NormalizedSearchResult(provider="exa", query="q", url="https://example.com/a?utm_source=x"),
        NormalizedSearchResult(provider="tavily", query="q", url="https://www.example.com/a"),
        NormalizedSearchResult(provider="exa", query="q", url="https://other.com/b"),
    ]
    provider = FakeProvider(results)
    gateway = SearchGateway([provider])
    policy = SearchPolicy(allowed_domains=("example.com", "other.com"))

    response = await gateway.search(
        "q",
        policy,
        focused_domains=["https://www.example.com/path"],
        highlight_query="evidence focus",
    )

    assert provider.calls[0][2] == ("example.com",)
    assert provider.calls[0][3] == "evidence focus"
    assert [result.normalized_url for result in response.results] == [
        "https://example.com/a",
        "https://other.com/b",
    ]
    assert len(response.duplicates) == 1
    assert response.rejected_results == []
    assert response.provider_counts == {"exa": 2}
    assert response.domain_counts == {"example.com": 1, "other.com": 1}


@pytest.mark.asyncio
async def test_gateway_rejects_focused_domains_outside_path_prefix_allowlist():
    gateway = SearchGateway([FakeProvider([])])

    with pytest.raises(SearchGatewayError, match="focused_domains must be a subset of allowed_domains"):
        await gateway.search(
            "q",
            SearchPolicy(allowed_domains=("aws.amazon.com/blogs/aws/",)),
            focused_domains=["aws.amazon.com/blogs/physical-ai/"],
        )


@pytest.mark.asyncio
async def test_gateway_uses_policy_allowlist_when_focused_domains_are_empty():
    provider = FakeProvider([])
    gateway = SearchGateway([provider])
    policy = SearchPolicy(allowed_domains=("example.com", "docs.example.com"))

    await gateway.search("q", policy)

    assert provider.calls[0][2] == ()


@pytest.mark.asyncio
async def test_gateway_enforces_allowed_domains_after_provider_return():
    results = [
        NormalizedSearchResult(provider="exa", query="q", url="https://example.com/a"),
        NormalizedSearchResult(provider="tavily", query="q", url="https://offpolicy.com/b"),
    ]
    gateway = SearchGateway([FakeProvider(results)])

    response = await gateway.search("q", SearchPolicy(allowed_domains=("example.com",)))

    assert [result.canonical_domain for result in response.results] == ["example.com"]
    assert [item.result.canonical_domain for item in response.rejected_results] == ["offpolicy.com"]
    assert response.provider_counts == {"exa": 1}
    assert response.domain_counts == {"example.com": 1}


@pytest.mark.asyncio
async def test_gateway_enforces_allowed_url_path_prefixes():
    results = [
        NormalizedSearchResult(provider="exa", query="q", url="https://aws.amazon.com/blogs/aws/x"),
        NormalizedSearchResult(provider="exa", query="q", url="https://aws.amazon.com/blogs/physical-ai/x"),
    ]
    gateway = SearchGateway([FakeProvider(results)])

    response = await gateway.search("q", SearchPolicy(allowed_domains=("aws.amazon.com/blogs/aws/",)))

    assert [result.normalized_url for result in response.results] == ["https://aws.amazon.com/blogs/aws/x"]
    assert [item.result.normalized_url for item in response.rejected_results] == [
        "https://aws.amazon.com/blogs/physical-ai/x"
    ]


@pytest.mark.asyncio
async def test_gateway_allows_any_path_for_pure_domain_allowlist():
    gateway = SearchGateway(
        [
            FakeProvider(
                [NormalizedSearchResult(provider="exa", query="q", url="https://aws.amazon.com/blogs/physical-ai/x")]
            )
        ]
    )

    response = await gateway.search("q", SearchPolicy(allowed_domains=("aws.amazon.com",)))

    assert [result.normalized_url for result in response.results] == ["https://aws.amazon.com/blogs/physical-ai/x"]


@pytest.mark.asyncio
async def test_gateway_accepts_no_scheme_path_prefix_allowlist():
    gateway = SearchGateway(
        [FakeProvider([NormalizedSearchResult(provider="exa", query="q", url="https://aws.amazon.com/blogs/aws/x")])]
    )

    response = await gateway.search("q", SearchPolicy(allowed_domains=("aws.amazon.com/blogs/aws",)))

    assert [result.normalized_url for result in response.results] == ["https://aws.amazon.com/blogs/aws/x"]


@pytest.mark.asyncio
async def test_gateway_accepts_all_domains_without_policy_constraints():
    results = [
        NormalizedSearchResult(provider="exa", query="q", url="https://example.com/a"),
        NormalizedSearchResult(provider="tavily", query="q", url="https://other.com/b"),
    ]
    gateway = SearchGateway([FakeProvider(results)])

    response = await gateway.search("q", SearchPolicy())

    assert [result.canonical_domain for result in response.results] == ["example.com", "other.com"]
    assert response.rejected_results == []


@pytest.mark.asyncio
async def test_gateway_records_provider_errors_without_failing_successful_provider(caplog):
    gateway = SearchGateway(
        [
            FakeProvider([NormalizedSearchResult(provider="exa", query="q", url="https://example.com/a")]),
            FailingProvider(name="tavily", error=PermissionError("quota exceeded")),
        ]
    )

    with caplog.at_level(logging.WARNING, logger="vanguard.research.search_gateway"):
        response = await gateway.search("q", SearchPolicy())

    assert [result.url for result in response.results] == ["https://example.com/a"]
    assert response.provider_counts == {"exa": 1}
    assert len(response.provider_errors) == 1
    assert response.provider_errors[0].provider == "tavily"
    assert response.provider_errors[0].error_type == "PermissionError"
    assert response.provider_errors[0].message == "quota exceeded"
    assert "Search provider failed: provider=tavily error_type=PermissionError error=quota exceeded" in caplog.text
    assert "Traceback" in caplog.text


@pytest.mark.asyncio
async def test_gateway_returns_empty_result_with_errors_when_all_providers_fail():
    gateway = SearchGateway(
        [
            FailingProvider(name="exa", error=RuntimeError("exa down")),
            FailingProvider(name="tavily", error=PermissionError("quota exceeded")),
        ]
    )

    response = await gateway.search("q", SearchPolicy())

    assert response.results == []
    assert response.provider_counts == {}
    assert response.domain_counts == {}
    assert [error.provider for error in response.provider_errors] == ["exa", "tavily"]


@pytest.mark.asyncio
async def test_gateway_rejects_focused_domains_without_allowlist():
    gateway = SearchGateway([FakeProvider([])])

    with pytest.raises(SearchGatewayError, match="allowed_domains is unconstrained"):
        await gateway.search("q", SearchPolicy(), focused_domains=["example.com"])


@pytest.mark.asyncio
async def test_gateway_rejects_focused_domains_outside_allowlist():
    gateway = SearchGateway([FakeProvider([])])

    with pytest.raises(SearchGatewayError, match="subset"):
        await gateway.search(
            "q",
            SearchPolicy(allowed_domains=("example.com",)),
            focused_domains=["other.com"],
        )


def test_diversity_helpers():
    policy = SearchPolicy(allowed_domains=("a.com", "b.com", "c.com"))
    results = [
        NormalizedSearchResult(provider="exa", query="q", url="https://a.com/1"),
        NormalizedSearchResult(provider="exa", query="q", url="https://a.com/2"),
        NormalizedSearchResult(provider="tavily", query="q", url="https://b.com/1"),
    ]

    assert count_domains(results) == {"a.com": 2, "b.com": 1}
    assert underrepresented_domains(policy, results) == ["b.com", "c.com"]
    assert "a.com" in (source_diversity_note(results, max_domain_share=0.5) or "")


def test_normalization_helpers():
    assert normalize_domain("https://www.Example.com:443/path") == "example.com"
    assert (
        normalize_url_for_deduplication("HTTPS://www.Example.com/path/?utm_source=x&b=2&a=1#section")
        == "https://example.com/path?a=1&b=2"
    )
    assert normalize_search_query(" latest\n  AI\tchips   guidance ") == "latest AI chips guidance"


def test_required_api_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="MISSING_SEARCH_KEY"):
        _required_api_key("MISSING_SEARCH_KEY", None)
