from __future__ import annotations

from datetime import date
import pytest
from types import SimpleNamespace

from vanguard import research
from vanguard.research import policy
from vanguard.research import node, tools
from vanguard.research.agent import filesystem_backend
from vanguard.search_gateway import NormalizedSearchResult, SearchGatewayResult, SearchPolicy


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


class FakeResearchAgent:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, payload, **kwargs):
        self.calls.append((payload, kwargs))
        kwargs["context"].recorder.record_search_results(
            [
                {
                    "provider": "exa",
                    "query": "search intent",
                    "url": "https://example.com/research",
                    "title": "Research source",
                    "summary": "Compact source summary.",
                    "raw_content_path": "/evidence/real-research.md",
                    "published_date": "2026-05-01",
                    "normalized_url": "https://example.com/research",
                    "canonical_domain": "example.com",
                }
            ],
            [
                {
                    "provider": "exa",
                    "url": "https://example.com/research",
                    "title": "Research source",
                    "path": "/evidence/real-research.md",
                    "content_sha256": "real123",
                    "content_characters": 47,
                }
            ],
        )
        return {
            "structured_response": research.ResearchAgentOutput(
                findings=["Compact source summary. [1]"],
                source_diversity_notes=["Recorder-backed metadata only."],
            )
        }


class FakeNoSearchResearchAgent:
    async def ainvoke(self, payload, **kwargs):
        return {
            "structured_response": research.ResearchAgentOutput(
                findings=["Unsupported finding."],
            )
        }


@pytest.mark.asyncio
async def test_conduct_research_invokes_agent_and_returns_compact_state(monkeypatch):
    agent = FakeResearchAgent()
    create_calls = []

    def fake_create_agent(config, backend=None):
        create_calls.append((config, backend))
        return agent

    monkeypatch.setattr(node, "create_research_agent", fake_create_agent)
    runtime = SimpleNamespace(context=SimpleNamespace())

    update = await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "allowed_domains": ["example.com"],
            "start_date": "2026-01-01",
            "end_date": date(2026, 12, 31),
            "research_findings": [],
            "research_sources": [],
            "source_diversity_notes": [],
        },
        runtime,
    )

    assert create_calls[0][0] is runtime.context
    payload, kwargs = agent.calls[0]
    assert "focused research brief" in payload["messages"][0].content
    assert kwargs["context"].filesystem_backend is create_calls[0][1]
    assert isinstance(kwargs["context"].recorder, research.ResearchRunRecorder)
    assert kwargs["context"].default_query == "search intent"
    assert kwargs["context"].default_highlight_query == "focused research brief"
    assert kwargs["context"].search_policy.allowed_domains == ("example.com",)
    assert kwargs["context"].search_policy.start_date == date(2026, 1, 1)
    assert kwargs["context"].search_policy.end_date == date(2026, 12, 31)
    assert "Compact source summary." in update["research_findings"][0]
    assert update["research_sources"] == [
        {
            "provider": "exa",
            "query": "search intent",
            "url": "https://example.com/research",
            "title": "Research source",
            "summary": "Compact source summary.",
            "raw_content_path": "/evidence/real-research.md",
            "published_date": "2026-05-01",
            "normalized_url": "https://example.com/research",
            "canonical_domain": "example.com",
        }
    ]
    assert "raw_content" not in update["research_sources"][0]
    assert update["evidence_artifacts"] == [
        {
            "provider": "exa",
            "url": "https://example.com/research",
            "title": "Research source",
            "path": "/evidence/real-research.md",
            "content_sha256": "real123",
            "content_characters": 47,
        }
    ]
    assert update["search_provider_counts"] == {"exa": 1}
    assert update["search_domain_counts"] == {"example.com": 1}
    assert update["source_diversity_notes"] == ["Recorder-backed metadata only."]


@pytest.mark.asyncio
async def test_conduct_research_requires_research_brief():
    with pytest.raises(ValueError, match="Missing research_brief"):
        await research.conduct_research(
            {"research_intent": "intent", "research_findings": []},
            SimpleNamespace(context=SimpleNamespace()),
        )


@pytest.mark.asyncio
async def test_conduct_research_requires_search_gateway_call(monkeypatch):
    monkeypatch.setattr(
        node,
        "create_research_agent",
        lambda config, backend=None: FakeNoSearchResearchAgent(),
    )

    with pytest.raises(ValueError, match="without calling search_gateway"):
        await research.conduct_research(
            {"research_intent": "intent", "research_brief": "brief"},
            SimpleNamespace(context=SimpleNamespace()),
        )


@pytest.mark.asyncio
async def test_search_gateway_tool_uses_constrained_gateway(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    backend = filesystem_backend(tmp_path)
    search_policy = SearchPolicy(
        allowed_domains=("example.com",),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    context = research.ResearchAgentContext(
        search_policy=search_policy,
        default_query="default query",
        default_highlight_query="default highlight",
        filesystem_backend=backend,
        recorder=research.ResearchRunRecorder(),
    )
    response = await tools._run_search_gateway_tool(
        query="custom query",
        highlight_query="custom highlight",
        context=context,
    )

    assert gateway.calls[0]["query"] == "custom query"
    assert gateway.calls[0]["highlight_query"] == "custom highlight"
    assert gateway.calls[0]["policy"] is search_policy
    assert response["provider_counts"] == {"exa": 1}
    assert response["results"][0]["raw_content_path"] is not None
    assert response["evidence_artifacts"][0]["content_characters"] == len(
        "This should not be serialized into graph state."
    )
    evidence_path = response["results"][0]["raw_content_path"]
    evidence = backend.read(evidence_path)
    assert evidence.error is None
    assert "This should not be serialized into graph state." in evidence.file_data["content"]
    assert response["evidence_artifacts"][0]["path"] == evidence_path
    assert context.recorder.sources() == response["results"]
    assert context.recorder.evidence_artifacts() == response["evidence_artifacts"]


@pytest.mark.asyncio
async def test_search_gateway_recorder_dedupes_across_tool_calls(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    context = research.ResearchAgentContext(
        search_policy=SearchPolicy(),
        default_query="default query",
        default_highlight_query="default highlight",
        filesystem_backend=filesystem_backend(tmp_path),
        recorder=research.ResearchRunRecorder(),
    )

    await tools._run_search_gateway_tool("first query", None, context)
    await tools._run_search_gateway_tool("second query", None, context)

    assert len(context.recorder.sources()) == 1
    assert len(context.recorder.evidence_artifacts()) == 1
    assert context.recorder.provider_counts() == {"exa": 1}
    assert context.recorder.domain_counts() == {"example.com": 1}


@pytest.mark.asyncio
async def test_search_gateway_tool_whitespace_query_uses_default(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    context = research.ResearchAgentContext(
        search_policy=SearchPolicy(),
        default_query="default query",
        default_highlight_query="default highlight",
        filesystem_backend=filesystem_backend(tmp_path),
        recorder=research.ResearchRunRecorder(),
    )

    await tools._run_search_gateway_tool("   ", None, context)

    assert gateway.calls[0]["query"] == "default query"


def test_search_gateway_tool_schema_hides_runtime_policy():
    assert set(research.search_gateway.args) == {"query", "highlight_query"}


def test_search_policy_from_state_uses_runtime_constraints():
    search_policy = policy._search_policy_from_state(
        {
            "research_intent": "intent",
            "allowed_domains": ["https://www.Example.com/path", "docs.example.com"],
            "start_date": "2025-01-01",
            "end_date": date(2025, 12, 31),
        }
    )

    assert search_policy.allowed_domains == ("example.com", "docs.example.com")
    assert search_policy.start_date == date(2025, 1, 1)
    assert search_policy.end_date == date(2025, 12, 31)


def test_search_query_from_state_prefers_intent_and_caps_length():
    long_intent = "word " * 120

    query = policy._search_query_from_state(
        {"research_intent": long_intent, "research_brief": "brief"},
        "brief",
    )

    assert len(query) <= policy.MAX_SEARCH_QUERY_CHARACTERS
    assert query.endswith("word")
