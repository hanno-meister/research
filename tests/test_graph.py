from __future__ import annotations

import asyncio
from datetime import date
import pytest
from types import SimpleNamespace
from typing import cast

from vanguard import research
from vanguard import planning
from vanguard.research import policy
from vanguard.research import node, tools
from vanguard.research.agent import filesystem_backend
from vanguard.search_gateway import NormalizedSearchResult, SearchGatewayResult, SearchPolicy
from vanguard.state import AgentState


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
                findings=[
                    research.ResearchFinding(
                        summary="Compact source summary.",
                        source_ids=["S1"],
                        evidence_paths=["/evidence/real-research.md"],
                    )
                ],
                source_diversity_notes=["Recorder-backed metadata only."],
            )
        }


class ConcurrentFakeResearchAgent(FakeResearchAgent):
    def __init__(self) -> None:
        super().__init__()
        self.active_calls = 0
        self.max_active_calls = 0

    async def ainvoke(self, payload, **kwargs):
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        await asyncio.sleep(0)
        result = await super().ainvoke(payload, **kwargs)
        self.active_calls -= 1
        return result


class FakeNoSearchResearchAgent:
    async def ainvoke(self, payload, **kwargs):
        return {
            "structured_response": research.ResearchAgentOutput(
                findings=[research.ResearchFinding(summary="Unsupported finding.")],
            )
        }


class FakePlanningModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self.response


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
    assert kwargs["context"].default_highlight_query == "focused research brief\nsearch intent"
    assert kwargs["context"].focused_domains == ()
    assert kwargs["context"].task_id == "task-1"
    assert kwargs["context"].search_policy.allowed_domains == ("example.com",)
    assert kwargs["context"].search_policy.start_date == date(2026, 1, 1)
    assert kwargs["context"].search_policy.end_date == date(2026, 12, 31)
    assert update["research_findings"] == [
        {
            "task_id": "task-1",
            "summary": "Compact source summary.",
            "source_ids": ["S1"],
            "evidence_paths": ["/evidence/real-research.md"],
        }
    ]
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
            "source_id": "S1",
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
    assert update["source_diversity_notes"] == ["task-1: Recorder-backed metadata only."]


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
        focused_domains=("example.com",),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
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
    assert gateway.calls[0]["focused_domains"] == ("example.com",)
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
    assert response["results"][0]["source_id"] == "S1"
    assert context.recorder.evidence_artifacts() == response["evidence_artifacts"]


@pytest.mark.asyncio
async def test_search_gateway_recorder_dedupes_across_tool_calls(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    context = research.ResearchAgentContext(
        search_policy=SearchPolicy(),
        default_query="default query",
        default_highlight_query="default highlight",
        focused_domains=(),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
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
        focused_domains=(),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
        filesystem_backend=filesystem_backend(tmp_path),
        recorder=research.ResearchRunRecorder(),
    )

    await tools._run_search_gateway_tool("   ", None, context)

    assert gateway.calls[0]["query"] == "default query"


@pytest.mark.asyncio
async def test_search_gateway_tool_enforces_search_budget(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    context = research.ResearchAgentContext(
        search_policy=SearchPolicy(),
        default_query="default query",
        default_highlight_query="default highlight",
        focused_domains=(),
        task_id="task-1",
        search_budget=research.ResearchSearchBudget(max_search_calls=1),
        filesystem_backend=filesystem_backend(tmp_path),
        recorder=research.ResearchRunRecorder(),
    )

    first_response = await tools._run_search_gateway_tool("first query", None, context)
    second_response = await tools._run_search_gateway_tool("second query", None, context)

    assert "error" not in first_response
    assert second_response["error"] == (
        "Search budget exhausted for task task-1; maximum 1 calls allowed."
    )
    assert second_response["results"] == []
    assert len(gateway.calls) == 1


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


def test_sanitized_tasks_filters_and_normalizes_domains():
    state = {
        "allowed_domains": ["https://www.Example.com/path", "docs.example.com"],
    }
    task = planning.ResearchTask(
        id="  task-1  ",
        objective="  Study source coverage  ",
        rationale="  why  ",
        boundaries=["  scope  "],
        key_questions=["  question  "],
        preferred_source_types=["  docs  "],
        focused_domains=["https://Example.com/article", "docs.example.com", "other.com"],
        expected_output="  compact output  ",
        effort="medium",
    )

    sanitized = planning._sanitized_tasks([task], cast(AgentState, state), "brief")

    assert sanitized[0].id == "task-1"
    assert sanitized[0].focused_domains == ["example.com", "docs.example.com"]
    assert sanitized[0].boundaries == ["scope"]
    assert sanitized[0].key_questions == ["question"]
    assert sanitized[0].preferred_source_types == ["docs"]
    assert sanitized[0].expected_output == "compact output"


def test_sanitized_tasks_falls_back_to_safe_task_when_empty():
    state = {"allowed_domains": ["https://www.Example.com/path"]}

    sanitized = planning._sanitized_tasks([], cast(AgentState, state), "Preserve this brief")

    assert len(sanitized) == 1
    assert sanitized[0].id == "task-1"
    assert sanitized[0].objective == "Preserve this brief"
    assert sanitized[0].focused_domains == ["example.com"]


@pytest.mark.asyncio
async def test_plan_research_uses_structured_model_and_returns_tasks(monkeypatch):
    response = planning.ResearchPlan(
        tasks=[
            planning.ResearchTask(
                id="task-1",
                objective="Find docs",
                rationale="Needed",
                expected_output="Compact output",
                effort="low",
            )
        ]
    )
    fake_model = FakePlanningModel(response)
    monkeypatch.setattr(planning, "ChatOpenAI", lambda **kwargs: fake_model)

    runtime = SimpleNamespace(
        context=SimpleNamespace(
            small_model="small",
            large_model="large",
            openai_base_url="http://example.invalid",
            azure_openai_api_key="dummy",
        )
    )

    update = await planning.plan_research(
        {
            "research_intent": "intent",
            "research_brief": "brief",
            "allowed_domains": ["example.com"],
        },
        runtime,
    )

    assert len(fake_model.calls) == 1
    assert "brief" in fake_model.calls[0][0].content
    assert update["research_tasks"][0]["objective"] == "Find docs"


@pytest.mark.asyncio
async def test_conduct_research_includes_research_tasks_in_prompt(monkeypatch):
    agent = FakeResearchAgent()

    monkeypatch.setattr(node, "create_research_agent", lambda config, backend=None: agent)
    runtime = SimpleNamespace(context=SimpleNamespace())

    await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "research_tasks": [
                {
                    "id": "task-1",
                    "objective": "Find docs",
                    "boundaries": ["docs only"],
                    "key_questions": ["What is the API?"],
                    "effort": "low",
                }
            ],
        },
        runtime,
    )

    payload, _kwargs = agent.calls[0]
    content = payload["messages"][0].content
    assert "focused research brief" in content
    assert "Focused worker task" in content
    assert "Find docs" in content


@pytest.mark.asyncio
async def test_conduct_research_runs_one_worker_per_task(monkeypatch):
    agent = FakeResearchAgent()

    monkeypatch.setattr(node, "create_research_agent", lambda config, backend=None: agent)
    runtime = SimpleNamespace(context=SimpleNamespace())

    update = await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "allowed_domains": ["example.com", "docs.example.com"],
            "research_tasks": [
                {
                    "id": "task-1",
                    "objective": "Find architecture docs",
                    "key_questions": ["What primitives exist?"],
                    "focused_domains": ["example.com"],
                    "expected_output": "Architecture findings",
                },
                {
                    "id": "task-2",
                    "objective": "Find persistence docs",
                    "key_questions": ["How are checkpoints used?"],
                    "focused_domains": ["docs.example.com"],
                    "expected_output": "Persistence findings",
                },
            ],
        },
        runtime,
    )

    assert len(agent.calls) == 2
    first_payload, first_kwargs = agent.calls[0]
    second_payload, second_kwargs = agent.calls[1]
    assert "Find architecture docs" in first_payload["messages"][0].content
    assert first_kwargs["context"].task_id == "task-1"
    assert first_kwargs["context"].focused_domains == ("example.com",)
    assert first_kwargs["context"].default_query == "Find architecture docs What primitives exist?"
    assert "Find persistence docs" in second_payload["messages"][0].content
    assert second_kwargs["context"].task_id == "task-2"
    assert second_kwargs["context"].focused_domains == ("docs.example.com",)
    assert [finding["task_id"] for finding in update["research_findings"]] == [
        "task-1",
        "task-2",
    ]
    assert update["research_findings"][0]["source_ids"] == ["S1"]
    assert update["research_findings"][0]["evidence_paths"] == [
        "/evidence/real-research.md"
    ]


@pytest.mark.asyncio
async def test_conduct_research_runs_workers_concurrently(monkeypatch):
    agent = ConcurrentFakeResearchAgent()

    monkeypatch.setattr(node, "create_research_agent", lambda config, backend=None: agent)
    runtime = SimpleNamespace(context=SimpleNamespace())

    await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "research_tasks": [
                {"id": "task-1", "objective": "Find architecture docs"},
                {"id": "task-2", "objective": "Find persistence docs"},
            ],
        },
        runtime,
    )

    assert agent.max_active_calls == 2
    assert [kwargs["context"].search_budget.max_search_calls for _, kwargs in agent.calls] == [
        node.MAX_SEARCH_CALLS_PER_WORKER,
        node.MAX_SEARCH_CALLS_PER_WORKER,
    ]
