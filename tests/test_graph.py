from __future__ import annotations

import pytest

from vanguard import research
from vanguard.search_gateway import NormalizedSearchResult, SearchGatewayResult


class FakeSearchGateway:
    def __init__(self) -> None:
        self.calls = []

    async def search(self, query, policy=None, focused_domains=None, highlight_query=None):
        self.calls.append(
            {
                "query": query,
                "policy": policy,
                "focused_domains": focused_domains,
                "highlight_query": highlight_query,
            }
        )
        results = [
            NormalizedSearchResult(
                provider="exa",
                query=query,
                url="https://example.com/research",
                title="Research source",
                summary="Compact source summary.",
                raw_content="This should not be serialized into graph state.",
                published_date="2026-05-01",
            ),
        ]
        return SearchGatewayResult(
            results=results,
            duplicates=[],
            provider_counts={"exa": 1},
            domain_counts={"example.com": 1},
        )


@pytest.mark.asyncio
async def test_conduct_research_uses_gateway_and_returns_compact_state(monkeypatch):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(research, "_default_search_gateway", lambda: gateway)

    update = await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "research_findings": [],
            "research_sources": [],
            "source_diversity_notes": [],
        }
    )

    assert gateway.calls[0]["query"] == "search intent"
    assert gateway.calls[0]["highlight_query"] == "focused research brief"
    assert "Compact source summary." in update["research_findings"][0]
    assert update["research_sources"] == [
        {
            "provider": "exa",
            "query": "search intent",
            "url": "https://example.com/research",
            "title": "Research source",
            "summary": "Compact source summary.",
            "published_date": "2026-05-01",
            "normalized_url": "https://example.com/research",
            "canonical_domain": "example.com",
        }
    ]
    assert "raw_content" not in update["research_sources"][0]
    assert update["search_provider_counts"] == {"exa": 1}
    assert update["search_domain_counts"] == {"example.com": 1}


@pytest.mark.asyncio
async def test_conduct_research_requires_research_brief():
    with pytest.raises(ValueError, match="Missing research_brief"):
        await research.conduct_research({"research_intent": "intent", "research_findings": []})


def test_search_query_from_state_prefers_intent_and_caps_length():
    long_intent = "word " * 120

    query = research._search_query_from_state(
        {"research_intent": long_intent, "research_brief": "brief"},
        "brief",
    )

    assert len(query) <= research.MAX_SEARCH_QUERY_CHARACTERS
    assert query.endswith("word")
