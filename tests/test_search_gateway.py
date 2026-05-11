from __future__ import annotations

from datetime import date

import pytest

from vanguard.search_gateway import (
    ExaSearchAdapter,
    NormalizedSearchResult,
    SearchGateway,
    SearchGatewayError,
    SearchPolicy,
    TavilySearchAdapter,
    count_domains,
    normalize_domain,
    normalize_url,
    source_diversity_note,
    underrepresented_domains,
    _required_api_key,
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
                    "highlights": {"max_characters": 750, "query": "focused evidence"},
                    "summary": True,
                },
                "include_domains": ["example.com"],
                "start_published_date": "2025-01-01",
            },
        )
    ]
    assert results[0].provider == "exa"
    assert results[0].summary == "Relevant excerpt"
    assert results[0].published_date == "2025-03-01"
    assert results[0].normalized_url == "https://example.com/a?id=1"


def test_exa_adapter_uses_compact_content_defaults():
    adapter = ExaSearchAdapter()

    assert adapter.num_results == 5
    assert adapter._contents("focused question") == {
        "highlights": {"max_characters": 1000, "query": "focused question"},
        "summary": True,
    }


@pytest.mark.asyncio
async def test_tavily_adapter_injects_focused_domains_over_policy_domains():
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


class FakeProvider:
    name = "fake"

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def search(self, query, policy, focused_domains=(), highlight_query=None):
        self.calls.append((query, policy, focused_domains, highlight_query))
        return self.results


@pytest.mark.asyncio
async def test_gateway_validates_focused_domains_and_dedupes_results():
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
    assert response.provider_counts == {"exa": 2}
    assert response.domain_counts == {"example.com": 1, "other.com": 1}


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
        normalize_url("HTTPS://www.Example.com/path/?utm_source=x&b=2&a=1#section")
        == "https://example.com/path?a=1&b=2"
    )


def test_required_api_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="MISSING_SEARCH_KEY"):
        _required_api_key("MISSING_SEARCH_KEY", None)
