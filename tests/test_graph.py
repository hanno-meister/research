from __future__ import annotations

import asyncio
from datetime import date
import re
import pytest
from types import SimpleNamespace
from typing import cast

from vanguard import research
from vanguard import planning
from vanguard import review
from vanguard.prompts import RESEARCH_PLAN_PROMPT
from vanguard.report_generation import build_report_bundle, final_report_generation
from vanguard.review import followup as review_followup
from vanguard.review import node as review_node
from vanguard.research import policy
from vanguard.research import node, tools
from vanguard.research.agent import filesystem_backend_for_config
from vanguard.research.search_gateway_models import (
    NormalizedSearchResult,
    SearchGatewayResult,
    SearchPolicy,
)
from vanguard.state import AgentState


def report_state(state: dict) -> AgentState:
    typed_state = cast(AgentState, state)
    if "report_bundle" in typed_state or not typed_state.get("research_reviews"):
        return typed_state
    return cast(AgentState, {**typed_state, "report_bundle": build_report_bundle(typed_state)["report_bundle"]})


class FakeSearchGateway:
    def __init__(self) -> None:
        self.calls = []
        self.results_per_provider = None

    def with_results_per_provider(self, results_per_provider: int):
        self.results_per_provider = results_per_provider
        return self

    async def search(self, query, policy=None, focused_domains=None, highlight_query=None):
        self.calls.append(
            {
                "query": query,
                "policy": policy,
                "focused_domains": focused_domains,
                "highlight_query": highlight_query,
                "results_per_provider": self.results_per_provider,
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


class FakeEmptySearchResearchAgent:
    async def ainvoke(self, payload, **kwargs):
        kwargs["context"].recorder.search_attempts += 1
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


class FakeReviewModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self.responses.pop(0)


def test_slim_source_for_review_keeps_only_review_fields_without_mutating_original():
    source = {
        "source_id": "S1",
        "title": "Research source",
        "summary": "Summary",
        "published_date": "2026-05-01",
        "canonical_domain": "example.com",
        "source_type": "primary",
        "source_quality": "high",
        "source_warnings": ["warning"],
        "provider": "exa",
        "query": "intent",
        "url": "https://example.com/research",
        "normalized_url": "https://example.com/research",
        "raw_content_path": "/evidence/real-research.md",
    }
    original = dict(source)

    slimmed = review_node.slim_source_for_review(source)

    assert set(slimmed) == review_node.REVIEW_SOURCE_FIELDS
    assert slimmed == {key: source[key] for key in review_node.REVIEW_SOURCE_FIELDS}
    assert source == original
    assert slimmed is not source


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
            "research_tasks": [
                {
                    "id": "task-1",
                    "objective": "search intent",
                    "expected_output": "Compact findings with source IDs and evidence paths.",
                }
            ],
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
            "source_type": "source",
            "source_quality": "high",
            "source_warnings": [],
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
            {
                "research_intent": "intent",
                "research_brief": "brief",
                "research_tasks": [
                    {
                        "id": "task-1",
                        "objective": "intent",
                        "expected_output": "Output",
                    }
                ],
            },
            SimpleNamespace(context=SimpleNamespace()),
        )


@pytest.mark.asyncio
async def test_conduct_research_drops_findings_when_search_records_no_sources(monkeypatch):
    monkeypatch.setattr(
        node,
        "create_research_agent",
        lambda config, backend=None: FakeEmptySearchResearchAgent(),
    )

    update = await research.conduct_research(
        {
            "research_intent": "intent",
            "research_brief": "brief",
            "research_tasks": [
                {
                    "id": "task-1",
                    "objective": "intent",
                    "expected_output": "Output",
                }
            ],
        },
        SimpleNamespace(context=SimpleNamespace()),
    )

    assert update["research_findings"] == []
    assert update["research_sources"] == []


@pytest.mark.asyncio
async def test_conduct_research_requires_planned_tasks():
    with pytest.raises(ValueError, match="Missing research_tasks"):
        await research.conduct_research(
            {"research_intent": "intent", "research_brief": "brief"},
            SimpleNamespace(context=SimpleNamespace()),
        )


@pytest.mark.asyncio
async def test_search_gateway_tool_uses_constrained_gateway(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda results_per_provider=5: gateway.with_results_per_provider(results_per_provider))
    backend = filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path))
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
        results_per_provider=10,
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
    assert gateway.calls[0]["results_per_provider"] == 10
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
async def test_search_gateway_tool_drops_invalid_focused_domains_and_keeps_valid_ones(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    backend = filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path))
    search_policy = SearchPolicy(
        allowed_domains=("venturebeat.com", "deeplearning.ai"),
    )

    context = research.ResearchAgentContext(
        search_policy=search_policy,
        default_query="default query",
        default_highlight_query="default highlight",
        focused_domains=("venturebeat.com", "blogs.nvidia.com"),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
        results_per_provider=10,
        filesystem_backend=backend,
        recorder=research.ResearchRunRecorder(),
    )
    await tools._run_search_gateway_tool("custom query", None, context)

    assert gateway.calls[0]["focused_domains"] == ("venturebeat.com",)


@pytest.mark.asyncio
async def test_search_gateway_tool_falls_back_to_allowed_universe_when_all_focused_invalid(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    backend = filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path))
    search_policy = SearchPolicy(
        allowed_domains=("venturebeat.com", "deeplearning.ai"),
    )

    context = research.ResearchAgentContext(
        search_policy=search_policy,
        default_query="default query",
        default_highlight_query="default highlight",
        focused_domains=("blogs.nvidia.com",),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
        results_per_provider=10,
        filesystem_backend=backend,
        recorder=research.ResearchRunRecorder(),
    )
    await tools._run_search_gateway_tool("custom query", None, context)

    assert gateway.calls[0]["focused_domains"] == ()


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
        results_per_provider=10,
        filesystem_backend=filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path)),
        recorder=research.ResearchRunRecorder(),
    )

    await tools._run_search_gateway_tool("first query", None, context)
    await tools._run_search_gateway_tool("second query", None, context)

    assert len(context.recorder.sources()) == 1
    assert len(context.recorder.evidence_artifacts()) == 1
    assert context.recorder.provider_counts() == {"exa": 1}
    assert context.recorder.domain_counts() == {"example.com": 1}


@pytest.mark.asyncio
async def test_search_gateway_tool_whitespace_query_returns_error(monkeypatch, tmp_path):
    gateway = FakeSearchGateway()
    monkeypatch.setattr(tools, "default_search_gateway", lambda: gateway)
    context = research.ResearchAgentContext(
        search_policy=SearchPolicy(),
        default_query="default query",
        default_highlight_query="default highlight",
        focused_domains=(),
        task_id=None,
        search_budget=research.ResearchSearchBudget(max_search_calls=2),
        results_per_provider=10,
        filesystem_backend=filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path)),
        recorder=research.ResearchRunRecorder(),
    )

    response = await tools._run_search_gateway_tool("   ", None, context)

    assert response["error"] == "search_gateway requires a non-empty query."
    assert response["results"] == []
    assert gateway.calls == []


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
        results_per_provider=10,
        filesystem_backend=filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path)),
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


def test_search_query_from_state_prefers_intent_and_normalizes_whitespace():
    long_intent = "word " * 120

    query = policy._search_query_from_state(
        {"research_intent": long_intent, "research_brief": "brief"},
        "brief",
    )

    assert query == long_intent.strip()
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
        focused_domains=["https://Example.com/path/article", "docs.example.com", "other.com"],
        depends_on=["1", "task-2", "task-1"],
        expected_output="  compact output  ",
        effort="medium",
    )

    sanitized = planning._sanitized_tasks([task], cast(AgentState, state), "brief")

    assert sanitized[0].id == "task-1"
    assert sanitized[0].focused_domains == ["example.com/path/", "docs.example.com"]
    assert sanitized[0].depends_on == ["task-2"]
    assert sanitized[0].boundaries == ["scope"]
    assert sanitized[0].key_questions == ["question"]
    assert sanitized[0].expected_output == "compact output"


def test_sanitized_tasks_rejects_empty_plans():
    state = {"allowed_domains": ["https://www.Example.com/path"]}

    with pytest.raises(ValueError, match="no usable research tasks"):
        planning._sanitized_tasks([], cast(AgentState, state), "Preserve this brief")


def test_sanitized_tasks_preserves_multiple_tasks():
    tasks = [
        planning.ResearchTask(
            id=f"task-{index}",
            objective=f"Narrow task {index}",
            rationale="Needed",
            expected_output="Output",
            effort="medium",
        )
        for index in range(1, planning.MAX_RESEARCH_TASKS + 2)
    ]

    sanitized = planning._sanitized_tasks(
        tasks,
        cast(AgentState, {"research_intent": "News about NVIDIA"}),
        "Find recent news about NVIDIA, including confirmed developments and limitations.",
    )

    assert len(sanitized) == planning.MAX_RESEARCH_TASKS + 1
    assert [task.id for task in sanitized] == [
        f"task-{index}" for index in range(1, planning.MAX_RESEARCH_TASKS + 2)
    ]


def test_feasibility_notes_do_not_add_domain_specific_assumptions():
    notes = planning.feasibility_notes_for_state(
        cast(
            AgentState,
            {
                "research_intent": "Evaluate NVIDIA world models",
                "allowed_domains": ["blogs.nvidia.com", "technologyreview.com"],
            },
        ),
        "Include evaluation methods, product maturity, and deployment barriers.",
    )

    assert notes == []


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


@pytest.mark.asyncio
async def test_conduct_research_runs_dependent_workers_after_prerequisites(monkeypatch):
    agent = ConcurrentFakeResearchAgent()

    monkeypatch.setattr(node, "create_research_agent", lambda config, backend=None: agent)
    runtime = SimpleNamespace(context=SimpleNamespace())

    await research.conduct_research(
        {
            "research_intent": "search intent",
            "research_brief": "focused research brief",
            "research_tasks": [
                {"id": "task-1", "objective": "Find systems"},
                {"id": "task-2", "objective": "Find benchmarks"},
                {"id": "task-3", "objective": "Synthesize recommendations", "depends_on": ["task-1", "task-2"]},
            ],
        },
        runtime,
    )

    assert agent.max_active_calls == 2
    assert [kwargs["context"].task_id for _, kwargs in agent.calls] == ["task-1", "task-2", "task-3"]


def test_topological_task_batches_rejects_cycles():
    with pytest.raises(ValueError, match="cycle"):
        node._topological_task_batches(
            [
                node.ResearchWorkerTask(id="task-1", objective="A", depends_on=("task-2",)),
                node.ResearchWorkerTask(id="task-2", objective="B", depends_on=("task-1",)),
            ]
        )


@pytest.mark.asyncio
async def test_review_research_reads_only_known_evidence_without_persisting_content(monkeypatch, tmp_path):
    backend = filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path))
    backend.write("/evidence/real-research.md", "important raw evidence content")
    fake_model = FakeReviewModel(
        [
            review.ResearchEvaluation(
                sufficient=False,
                coverage_assessment="Need to inspect evidence.",
                evidence_to_read=[
                    review.EvidenceReadRequest(
                        source_id="S1",
                        reason="Verify key claim.",
                    ),
                    review.EvidenceReadRequest(
                        source_id="S999",
                        reason="Unknown source should be ignored.",
                    ),
                ],
            ),
            review.ResearchEvaluation(
                sufficient=True,
                coverage_assessment="Evidence supports the finding.",
                required_report_topics=["Marble", "WorldScore"],
                coverage_gaps=["Genie 3 not found in allowed sources"],
            ),
        ]
    )
    monkeypatch.setattr(review_node, "ChatOpenAI", lambda **kwargs: fake_model)

    update = await review.review_research(
        {
            "research_intent": "intent",
            "research_brief": "brief",
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Finding",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/real-research.md"],
                }
            ],
            "research_sources": [
                {
                    "provider": "exa",
                    "query": "intent",
                    "url": "https://example.com/research",
                    "title": "Research source",
                    "summary": "Summary",
                    "raw_content_path": "/evidence/real-research.md",
                    "published_date": "2026-05-01",
                    "normalized_url": "https://example.com/research",
                    "canonical_domain": "example.com",
                    "source_id": "S1",
                }
            ],
            "evidence_artifacts": [
                {
                    "provider": "exa",
                    "url": "https://example.com/research",
                    "title": "Research source",
                    "path": "/evidence/real-research.md",
                    "content_sha256": "abc123",
                    "content_characters": 30,
                }
            ],
        },
        SimpleNamespace(context=SimpleNamespace(large_model="large", openai_base_url="url", azure_openai_api_key="key", evidence_root=tmp_path)),
    )

    assert len(fake_model.calls) == 2
    assert update["evidence_read_records"] == [
        {
            "source_id": "S1",
            "path": "/evidence/real-research.md",
            "reason": "Verify key claim.",
            "content_characters": len("important raw evidence content"),
        }
    ]
    assert "content" not in update["evidence_read_records"][0]
    assert update["review_round"] == 1
    assert len(update["research_reviews"]) == 1
    assert update["research_reviews"][0]["evidence_read"] == update["evidence_read_records"]
    assert update["research_reviews"][0]["required_report_topics"] == ["Marble", "WorldScore"]
    assert update["research_reviews"][0]["coverage_gaps"] == ["Genie 3 not found in allowed sources"]


@pytest.mark.asyncio
async def test_repair_research_runs_bounded_follow_up_workers(monkeypatch, tmp_path):
    agent = FakeResearchAgent()
    monkeypatch.setattr(review_followup, "create_research_agent", lambda config, backend=None: agent)
    monkeypatch.setattr(
        review_followup,
        "filesystem_backend_for_config",
        lambda _config: filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path)),
    )
    monkeypatch.setattr(review_followup, "MAX_FOLLOW_UP_WORKERS", 1)
    monkeypatch.setattr(review_followup, "MAX_FOLLOW_UP_SEARCHES", 1)

    update = await review.repair_research(
        {
            "research_intent": "intent",
            "research_brief": "brief",
            "allowed_domains": ["example.com"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-20",
            "research_findings": [],
            "research_sources": [],
            "evidence_artifacts": [],
            "review_round": 1,
            "research_reviews": [
                {
                    "round": 1,
                    "sufficient": False,
                    "follow_up_tasks": [
                        planning.ResearchTask(
                            id="follow-1",
                            objective="Find persistence docs",
                            rationale="Close coverage gap.",
                            expected_output="Persistence finding.",
                            effort="low",
                        ).model_dump(),
                        planning.ResearchTask(
                            id="follow-2",
                            objective="Find deployment docs",
                            rationale="Extra task should be capped.",
                            expected_output="Deployment finding.",
                            effort="low",
                        ).model_dump(),
                    ],
                }
            ],
        },
        SimpleNamespace(context=SimpleNamespace(large_model="large", openai_base_url="url", azure_openai_api_key="key")),
    )

    assert len(agent.calls) == 1
    payload, kwargs = agent.calls[0]
    assert "Find persistence docs" in payload["messages"][0].content
    assert kwargs["context"].search_budget.max_search_calls == 1
    assert kwargs["context"].results_per_provider == 5
    assert kwargs["context"].search_policy.allowed_domains == ("example.com",)
    assert kwargs["context"].search_policy.start_date.isoformat() == "2026-05-01"
    assert kwargs["context"].search_policy.end_date.isoformat() == "2026-05-20"
    assert update["research_findings"] == [
        {
            "task_id": "follow-up-1",
            "summary": "Compact source summary.",
            "source_ids": ["S1"],
            "evidence_paths": ["/evidence/real-research.md"],
            "produced_by": "repair_research:round-1",
            "repair_task_id": "follow-up-1",
        }
    ]
    assert "source_diversity_notes" not in update
    assert update["repair_logs"][0]["tasks_run"] == ["follow-up-1"]
    assert update["repair_logs"][0]["tasks_succeeded"] == ["follow-up-1"]
    assert update["repair_logs"][0]["source_diversity_notes"] == ["Recorder-backed metadata only."]
    assert update["repair_logs"][0]["produced_source_ids"] == ["S1"]
    assert update["repair_logs"][0]["produced_finding_count"] == 1
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
            "source_type": "source",
            "source_quality": "high",
            "source_warnings": [],
            "source_id": "S1",
            "produced_by": "repair_research:round-1",
            "repair_task_id": "follow-up-1",
        }
    ]


@pytest.mark.asyncio
async def test_follow_up_worker_uses_follow_up_context_when_budget_matches_default(tmp_path):
    agent = FakeResearchAgent()
    recorder = research.ResearchRunRecorder()
    task = review_followup.ResearchWorkerTask(
        id="follow-up-1",
        objective="Find focused evidence",
        focused_domains=("example.com",),
        expected_output="Evidence.",
    )

    await review_followup.run_research_worker_with_budget(
        agent=agent,
        state=cast(
            AgentState,
            {
                "research_intent": "intent",
                "research_brief": "brief",
                "allowed_domains": ["example.com"],
                "start_date": "2026-05-01",
                "end_date": "2026-05-20",
            },
        ),
        research_brief="brief",
        task=task,
        backend=filesystem_backend_for_config(SimpleNamespace(evidence_root=tmp_path)),
        recorder=recorder,
        max_search_calls=2,
    )

    assert len(agent.calls) == 1
    _payload, kwargs = agent.calls[0]
    assert kwargs["context"].focused_domains == ("example.com",)
    assert kwargs["context"].search_budget.max_search_calls == 2
    assert kwargs["context"].results_per_provider == 5
    assert kwargs["context"].search_policy.start_date.isoformat() == "2026-05-01"
    assert kwargs["context"].search_policy.end_date.isoformat() == "2026-05-20"


def test_follow_up_worker_tasks_treats_focused_domains_as_hints():
    tasks = [
        planning.ResearchTask(
            id="blocked",
            objective="Needs unavailable source",
            rationale="Blocked",
            focused_domains=["sec.gov"],
            expected_output="Output",
            effort="high",
        ),
        planning.ResearchTask(
            id="allowed",
            objective="Use allowed source",
            rationale="Allowed",
            focused_domains=["example.com"],
            expected_output="Output",
            effort="low",
        ),
    ]

    worker_tasks = review_followup.follow_up_worker_tasks(
        tasks,
        cast(AgentState, {"allowed_domains": ["example.com"], "research_brief": "brief"}),
        remaining_workers=2,
        remaining_workers_by_search_budget=2,
    )

    assert [task.id for task in worker_tasks] == ["follow-up-1", "follow-up-2"]
    assert worker_tasks[0].focused_domains == ()
    assert worker_tasks[1].focused_domains == ("example.com",)


def test_final_report_filters_caveats_and_promotes_follow_up_findings():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_tasks": [
                {"id": "task-1", "objective": "Initial pattern evidence"},
            ],
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Plan-and-execute is an official current LangGraph pattern.",
                    "source_ids": ["S24"],
                    "evidence_paths": ["/evidence/mismatched.md"],
                },
                {
                    "task_id": "task-5",
                    "summary": "Plan-and-execute should be framed as archival or Deep Agents-maintained.",
                    "source_ids": ["S90"],
                    "evidence_paths": ["/evidence/deep-agents.md"],
                },
                {
                    "task_id": "task-1",
                    "summary": "Reducers support parallel state merging.",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/graph-api.md"],
                },
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "coverage_assessment": "Follow-up repaired weak pattern evidence.",
                    "source_quality_assessment": "Official docs are strong; pattern examples need caveats.",
                    "contradiction_notes": [
                        "S24 is mismatched and should not support current plan-and-execute claims."
                    ],
                    "weak_or_unsupported_findings": [
                        "Planner-executor as current official guidance is weak when citing S24."
                    ],
                }
            ],
            "evidence_read_records": [
                {
                    "source_id": "S24",
                    "path": "/evidence/mismatched.md",
                    "reason": "Verify mismatch.",
                    "content_characters": 4000,
                }
            ],
            "source_diversity_notes": ["task-1: mostly official docs"],
        }
    ))

    report = update["final_report"]
    assert report.startswith("# Trend Report: World Generation Models for Spatial Computing")
    assert "## Summary" in report
    assert "## Executive Summary" not in report
    assert "## Trending Technologies" in report
    assert "## Team Suggestions" in report
    assert "## Deep Dive" in report
    assert "Reducers support parallel state merging." in report
    assert "Plan-and-execute should be framed as archival" in report
    assert "Plan-and-execute is an official current LangGraph pattern." not in report
    assert "## Selected Sources" in report
    assert "Lower-confidence, contradictory, or insufficiently supported items were omitted" not in report
    assert "S24 is mismatched" not in report
    assert "Raw evidence inspected for S24" not in report
    assert "/evidence/" not in report


def test_final_report_gracefully_handles_missing_review():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Compact finding.",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/other.md"],
                }
            ],
        }
    ))

    report = update["final_report"]
    assert "# Research Incomplete" in report
    assert "No evidence-quality check was available" in report
    assert "Compact finding." in report
    assert "sources: S1" not in report


def test_incomplete_report_is_concise_public_and_omits_evidence_paths():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_tasks": [{"id": "task-1", "objective": "Initial"}],
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Supported provisional finding.",
                    "source_ids": ["S3"],
                    "evidence_paths": ["/evidence/other.md"],
                },
                {
                    "task_id": "task-1",
                    "summary": "Remove this review-control note from the final report.",
                    "source_ids": ["S2"],
                },
            ],
            "research_reviews": [
                {
                    "sufficient": False,
                    "coverage_assessment": "Market reaction coverage is incomplete.",
                    "contradiction_notes": [
                        "Market reaction coverage is incomplete.",
                        "S1 should not anchor claims from /evidence/source.md without stronger corroboration.",
                    ],
                    "weak_or_unsupported_findings": [],
                    "follow_up_tasks": [{"id": "task-2", "objective": "Check primary filings."}],
                }
            ],
            "research_sources": [{"source_id": "S1", "title": "Source", "canonical_domain": "example.com"}],
            "evidence_artifacts": [{"source_id": "S1", "path": "/evidence/source.md"}],
        }
    ))

    report = update["final_report"]
    assert report.startswith("# Research Incomplete")
    assert report.count("Market reaction coverage is incomplete.") == 1
    assert "Supported provisional finding." in report
    assert "Remove this review-control note" in report
    assert "does not sufficiently support claims from evidence artifact" in report
    assert "Check primary filings." in report
    assert "S1" not in report
    assert "/evidence/" not in report


def test_build_report_bundle_filters_and_validates_selected_items():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Primary supported claim", "source_ids": ["S1", "S2"]},
                    {"summary": "Excluded claim", "source_ids": ["S3"]},
                    {"summary": "Dangling claim", "source_ids": ["S9"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Primary", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Caution", "url": "https://example.com/2"},
                    {"source_id": "S3", "title": "Excluded", "url": "https://example.com/3"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "use", "reason": "primary"},
                            {"source_id": "S2", "status": "caution", "reason": "weak"},
                            {"source_id": "S3", "status": "exclude", "reason": "bad"},
                        ],
                        "selected_report_findings": [
                            {"finding_id": "F1", "status": "use", "reason": "ok"},
                            {"finding_id": "F2", "status": "exclude", "reason": "bad"},
                            {"finding_id": "F3", "status": "use", "reason": "dangling"},
                        ],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert [source["source_id"] for source in bundle["sources"]] == ["S1", "S2"]
    assert [finding["finding_id"] for finding in bundle["findings"]] == ["F1"]
    assert bundle["findings"][0]["citation_source_ids"] == ["S1", "S2"]
    assert any(caveat["type"] == "dropped_finding_without_kept_citations" for caveat in bundle["methodology_caveats"])


def test_build_report_bundle_prunes_excluded_finding_citations_with_caveat():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Mixed support claim", "source_ids": ["S1", "S2", "S3"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Use", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Caution", "url": "https://example.com/2"},
                    {"source_id": "S3", "title": "Excluded", "url": "https://example.com/3"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "use", "reason": "primary"},
                            {"source_id": "S2", "status": "caution", "reason": "weak"},
                            {"source_id": "S3", "status": "exclude", "reason": "duplicate"},
                        ],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert [finding["finding_id"] for finding in bundle["findings"]] == ["F1"]
    assert bundle["findings"][0]["citation_source_ids"] == ["S1", "S2"]
    assert {
        "type": "pruned_finding_citations",
        "finding_id": "F1",
        "pruned_source_ids": ["S3"],
    } in bundle["methodology_caveats"]


def test_build_report_bundle_drops_finding_with_only_excluded_citations():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Unsupported after exclusion", "source_ids": ["S1", "S2"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Excluded 1", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Excluded 2", "url": "https://example.com/2"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "exclude", "reason": "duplicate"},
                            {"source_id": "S2", "status": "exclude", "reason": "duplicate"},
                        ],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert bundle["findings"] == []
    assert any(caveat["type"] == "dropped_finding_without_kept_citations" for caveat in bundle["methodology_caveats"])


def test_build_report_bundle_keeps_use_citations_unchanged_without_pruning_caveat():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Fully supported claim", "source_ids": ["S1", "S2"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Use 1", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Use 2", "url": "https://example.com/2"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "use", "reason": "primary"},
                            {"source_id": "S2", "status": "use", "reason": "primary"},
                        ],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert [finding["finding_id"] for finding in bundle["findings"]] == ["F1"]
    assert bundle["findings"][0]["citation_source_ids"] == ["S1", "S2"]
    assert not any(caveat["type"] == "pruned_finding_citations" for caveat in bundle["methodology_caveats"])


def test_build_report_bundle_prunes_banned_finding_citations_with_caveat():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Mixed banned support claim", "source_ids": ["S1", "S2"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Use", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Banned", "url": "https://example.com/2"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "weak_or_unsupported_findings": ["Duplicate source S2 should not support claims."],
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "use", "reason": "primary"},
                            {"source_id": "S2", "status": "use", "reason": "duplicate"},
                        ],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert [finding["finding_id"] for finding in bundle["findings"]] == ["F1"]
    assert bundle["findings"][0]["citation_source_ids"] == ["S1"]
    assert {
        "type": "pruned_finding_citations",
        "finding_id": "F1",
        "pruned_source_ids": ["S2"],
    } in bundle["methodology_caveats"]


def test_build_report_bundle_drops_finding_when_all_citations_are_banned():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "research_findings": [
                    {"summary": "Fully banned claim", "source_ids": ["S1", "S2"]},
                ],
                "research_sources": [
                    {"source_id": "S1", "title": "Banned 1", "url": "https://example.com/1"},
                    {"source_id": "S2", "title": "Banned 2", "url": "https://example.com/2"},
                ],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "contradiction_notes": ["Contradictory support from S1 and S2."],
                        "selected_report_sources": [
                            {"source_id": "S1", "status": "use", "reason": "selected"},
                            {"source_id": "S2", "status": "use", "reason": "selected"},
                        ],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert bundle["findings"] == []
    assert any(caveat["type"] == "dropped_banned_finding" for caveat in bundle["methodology_caveats"])


def test_build_report_bundle_demotes_missing_evidence_reads_and_keeps_repair_caveats():
    update = build_report_bundle(
        cast(
            AgentState,
            {
                "review_round": 2,
                "research_findings": [
                    {
                        "summary": "Repair claim about topic alpha",
                        "source_ids": ["S1"],
                        "produced_by": "repair_research:round-1",
                        "repair_task_id": "follow-up-1",
                    }
                ],
                "research_sources": [{"source_id": "S1", "title": "Only source", "url": "https://example.com/1"}],
                "evidence_read_records": [],
                "repair_logs": [{"round": 1, "source_diversity_notes": ["Follow-up surfaced only vendor sources."]}],
                "research_reviews": [
                    {
                        "sufficient": True,
                        "required_report_topics": ["topic alpha"],
                        "evidence_to_read": [{"source_id": "S1", "reason": "verify"}],
                        "selected_report_sources": [{"source_id": "S1", "status": "use", "reason": "ok"}],
                        "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "ok"}],
                    }
                ],
            },
        )
    )

    bundle = update["report_bundle"]
    assert bundle["findings"][0]["status"] == "caution"
    assert bundle["findings"][0]["provenance"] == {
        "produced_by": "repair_research:round-1",
        "repair_task_id": "follow-up-1",
    }
    caveat_types = {caveat["type"] for caveat in bundle["methodology_caveats"]}
    assert "missing_evidence_read" in caveat_types
    assert "repair_source_diversity" in caveat_types


def test_insufficient_review_with_usable_evidence_renders_partial_report():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Supported caveated trend finding.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Useful source", "url": "https://example.com/source", "canonical_domain": "example.com"},
            ],
            "research_reviews": [
                {
                    "sufficient": False,
                    "coverage_assessment": "Enough evidence for a caveated synthesis, but named systems remain undercovered.",
                    "source_quality_assessment": "Sources are useful but incomplete.",
                    "coverage_gaps": ["Missing primary evidence for named systems."],
                    "selected_report_sources": [{"source_id": "S1", "status": "use", "reason": "supports trend"}],
                    "selected_report_findings": [{"finding_id": "F1", "status": "use", "reason": "supported"}],
                }
            ],
        }
    ))

    report = update["final_report"]
    assert update["report_status"] == "partial"
    assert not report.startswith("# Research Incomplete")
    assert "> Partial report: Enough evidence for a caveated synthesis" in report
    assert "Supported caveated trend finding." in report
    assert "## Confidence and Gaps" in report
    assert "Missing primary evidence for named systems." in report


def test_core_unanswerable_review_stays_incomplete_even_with_evidence():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [{"summary": "Some finding.", "source_ids": ["S1"]}],
            "research_sources": [{"source_id": "S1", "title": "Source", "canonical_domain": "example.com"}],
            "research_reviews": [
                {
                    "sufficient": False,
                    "core_brief_answerable": False,
                    "selected_report_sources": [{"source_id": "S1", "status": "use", "reason": "ok"}],
                }
            ],
        }
    ))

    assert update["report_status"] == "incomplete"
    assert update["final_report"].startswith("# Research Incomplete")


def test_required_topics_alone_do_not_create_partial_report():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [],
            "research_sources": [],
            "research_reviews": [{"sufficient": False, "required_report_topics": ["Topic"]}],
        }
    ))

    assert update["report_status"] == "incomplete"
    assert update["final_report"].startswith("# Research Incomplete")


def test_prompts_include_general_source_quality_invariants():
    assert "source-quality expectations" in RESEARCH_PLAN_PROMPT

    assert "Do not mark research sufficient just because sources exist" in review_node.REVIEW_RESEARCH_PROMPT
    assert "Weakness notes are control data" in review_node.REVIEW_RESEARCH_PROMPT


def test_final_report_filters_review_caveats_without_source_id_substring_matches():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_tasks": [{"id": "task-1", "objective": "Initial"}],
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Stable S1-backed finding.",
                    "source_ids": ["S1"],
                },
                {
                    "task_id": "task-1",
                    "summary": "Weak S10-backed finding.",
                    "source_ids": ["S10"],
                },
                {
                    "task_id": "task-7",
                    "summary": "Follow-up finding from review-requested task.",
                    "source_ids": ["S20"],
                },
            ],
            "research_reviews": [
                {
                    "sufficient": False,
                    "source_quality_assessment": "Earlier evidence-quality concern.",
                    "contradiction_notes": ["S10 is weak and should be caveated."],
                    "weak_or_unsupported_findings": [],
                    "follow_up_tasks": [
                        {
                            "id": "task-7",
                            "objective": "Repair evidence",
                        }
                    ],
                },
                {
                    "sufficient": True,
                    "coverage_assessment": "Follow-up completed.",
                    "contradiction_notes": [],
                    "weak_or_unsupported_findings": [],
                    "follow_up_tasks": [],
                },
            ],
            "source_diversity_notes": ["follow-up task-7: targeted repair"],
        }
    ))

    report = update["final_report"]
    assert "Stable S1-backed finding." in report
    assert "Weak S10-backed finding." in report
    assert "S10 is weak and should be caveated." not in report
    assert "Follow-up finding from review-requested task." in report
    assert "Earlier evidence-quality concern." not in report
    assert "Source quality is adequate" not in report


def test_final_report_caveat_takes_precedence_over_follow_up_section():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_tasks": [{"id": "task-1", "objective": "Initial"}],
            "research_findings": [
                {
                    "task_id": "task-7",
                    "summary": "Follow-up finding that still needs caveat.",
                    "source_ids": ["S20"],
                }
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "contradiction_notes": ["S20 remains uncertain."],
                    "weak_or_unsupported_findings": [],
                    "follow_up_tasks": [{"id": "task-7", "objective": "Repair"}],
                }
            ],
            "source_diversity_notes": ["follow-up task-7: targeted repair"],
        }
    ))

    report = update["final_report"]
    assert "## Corrections and Updates" not in report
    assert "Follow-up finding that still needs caveat." not in report
    assert "Lower-confidence, contradictory, or insufficiently supported items were omitted" not in report


def test_final_report_ignores_colliding_follow_up_diversity_note_task_ids():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_tasks": [{"id": "task-1", "objective": "Initial"}],
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Original task finding should stay key finding.",
                    "source_ids": ["S1"],
                },
                {
                    "task_id": "task-8",
                    "summary": "Review-record follow-up should still be promoted.",
                    "source_ids": ["S8"],
                },
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "follow_up_tasks": [{"id": "task-8", "objective": "Repair"}],
                }
            ],
            "source_diversity_notes": [
                "follow-up task-1: colliding note should not promote originals"
            ],
        }
    ))

    report = update["final_report"]
    assert "## Corrections and Updates" not in report
    assert "Original task finding should stay key finding." in report
    assert "Review-record follow-up should still be promoted." in report


def test_final_report_preserves_finding_order_without_heuristic_text_filtering():
    update = final_report_generation(report_state(
        {
            "research_intent": "Find recent Nvidia news",
            "research_tasks": [{"id": "task-1", "objective": "Recent Nvidia news"}],
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "Recent newsletter coverage says NVIDIA is using AI to design chips.",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/newsletter.md"],
                },
                {
                    "task_id": "task-1",
                    "summary": "Flag CES 2026 and roundup pages as out of scope for this task because they are not individually verified.",
                    "source_ids": ["S2"],
                    "evidence_paths": ["/evidence/feed.md"],
                },
                {
                    "task_id": "task-1",
                    "summary": "Reuters reported NVIDIA would invest up to $2.1B in IREN as part of an AI data-center deal.",
                    "source_ids": ["S3"],
                    "evidence_paths": ["/evidence/reuters.md"],
                },
            ],
            "research_sources": [
                {
                    "source_id": "S1",
                    "title": "AI-guided chip design newsletter",
                    "url": "https://www.deeplearning.ai/the-batch/issue-352",
                    "canonical_domain": "deeplearning.ai",
                    "published_date": "2026-05-08",
                },
                {
                    "source_id": "S2",
                    "title": "NVIDIA roundup feed",
                    "url": "https://blogs.nvidia.com/feed/",
                    "canonical_domain": "blogs.nvidia.com",
                    "published_date": None,
                },
                {
                    "source_id": "S3",
                    "title": "Nvidia to invest in IREN data center deal",
                    "url": "https://www.reuters.com/business/nvidia-invest-iren-2026-05-07/",
                    "canonical_domain": "reuters.com",
                    "published_date": "2026-05-07",
                },
            ],
            "research_reviews": [{"sufficient": True}],
            "search_provider_counts": {"exa": 1, "tavily": 2},
        }
    ))

    report = update["final_report"]
    assert report.startswith("# Trend Report: World Generation Models for Spatial Computing")
    assert "## Summary" in report
    assert "### Recent newsletter coverage says NVIDIA is using AI" in report
    assert "Recent newsletter coverage says NVIDIA is using AI to design chips." in report
    assert "### Reuters reported NVIDIA would invest up to $2.1B" in report
    assert "Reuters reported NVIDIA would invest up to $2.1B in IREN as part of an AI data-center deal." in report
    assert "https://www.deeplearning.ai/the-batch/issue-352" in report
    assert "https://blogs.nvidia.com/feed/" in report
    assert "https://www.reuters.com/business/nvidia-invest-iren-2026-05-07/" in report
    assert "Flag CES 2026" in report
    assert "/evidence/" not in report
    assert "## Major Developments\n\n" not in report
    assert report.index("Recent newsletter coverage") < report.index("Reuters reported")
    assert "Nvidia to invest in IREN data center deal" in report


def test_final_report_keeps_overlapping_findings_and_uses_public_citations():
    update = final_report_generation(report_state(
        {
            "research_intent": "Research product launch",
            "research_findings": [
                {
                    "task_id": "task-1",
                    "summary": "The company launched a new platform for enterprise customers.",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/source.md"],
                },
                {
                    "task_id": "task-2",
                    "summary": "The company launched a new enterprise platform for customers and partners.",
                    "source_ids": ["S1"],
                    "evidence_paths": ["/evidence/source.md"],
                },
            ],
            "research_sources": [
                {
                    "source_id": "S1",
                    "title": "Official launch post",
                    "url": "https://example.com/launch",
                    "canonical_domain": "example.com",
                    "published_date": "2026-05-01",
                }
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert report.startswith("# Trend Report: World Generation Models for Spatial Computing")
    assert "The company launched a new platform for enterprise customers." in report
    assert "The company launched a new enterprise platform" in report
    assert "Source: https://example.com/launch" in report
    assert "[1]" not in report
    assert "Official launch post" in report
    assert "S1" not in report
    assert "/evidence/" not in report


def test_final_report_key_takeaways_populate_when_draft_is_empty():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"task_id": "task-1", "summary": "First finding.", "source_ids": ["S1"]},
                {"task_id": "task-2", "summary": "Second finding.", "source_ids": ["S2"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Source one", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Source two", "canonical_domain": "example.com"},
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert "## Summary" in report
    assert "No high-confidence findings were available." not in report
    assert "## Selected Sources" in report


def test_final_report_selected_sources_are_numbered_and_uncapped():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"task_id": "task-1", "summary": f"Finding {i}.", "source_ids": [f"S{i}"]}
                for i in range(1, 18)
            ],
            "research_sources": [
                {"source_id": f"S{i}", "title": f"Source {i}", "canonical_domain": "example.com"}
                for i in range(1, 18)
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert "[17]" not in report
    assert report.count("Source ") >= 17


def test_final_report_respects_selected_report_sources_policy():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"task_id": "task-1", "summary": "Useable claim from source one.", "source_ids": ["S1"]},
                {"task_id": "task-1", "summary": "Cautionary claim from source two.", "source_ids": ["S2"]},
                {"task_id": "task-1", "summary": "Excluded claim from source three.", "source_ids": ["S3"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Use source", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Caution source", "canonical_domain": "example.com"},
                {"source_id": "S3", "title": "Exclude source", "canonical_domain": "example.com"},
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "selected_report_sources": [
                        {"source_id": "S1", "status": "use", "reason": "ok"},
                        {"source_id": "S2", "status": "caution", "reason": "limited"},
                        {"source_id": "S3", "status": "exclude", "reason": "bad"},
                        {"source_id": "S9", "status": "use", "reason": "unknown"},
                    ],
                }
            ],
        }
    ))

    report = update["final_report"]
    assert "Useable claim from source one." in report
    assert "Cautionary claim from source two." in report
    assert "Excluded claim from source three." not in report
    assert "Exclude source" not in report
    assert "Caution source" in report
    assert "a recorded source" not in report
    assert "S9" not in report


def test_final_report_contiguous_source_numbering_skips_unused_and_excluded_sources():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "First cited finding.", "source_ids": ["S1"]},
                {"summary": "Second cited finding.", "source_ids": ["S3"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "One", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Two", "canonical_domain": "example.com"},
                {"source_id": "S3", "title": "Three", "canonical_domain": "example.com"},
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "selected_report_sources": [
                        {"source_id": "S1", "status": "use", "reason": "ok"},
                        {"source_id": "S2", "status": "exclude", "reason": "bad"},
                        {"source_id": "S3", "status": "caution", "reason": "limited"},
                    ],
                }
            ],
        }
    ))

    report = update["final_report"]
    assert "One (example.com)" in report
    assert "Three (example.com)" in report
    assert "[3]" not in report
    assert "## Selected Sources" in report
    assert "One (example.com)" in report
    assert "Three (example.com)" in report


def test_final_report_uses_finding_selection_and_only_cited_sources_in_sources_list():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Old stale finding.", "source_ids": ["S1"]},
                {"summary": "Follow-up corrected finding.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Shared source", "canonical_domain": "example.com"},
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "selected_report_sources": [{"source_id": "S1", "status": "use", "reason": "ok"}],
                    "selected_report_findings": [
                        {"finding_id": "F2", "status": "use", "reason": "supersedes"},
                    ],
                }
            ],
        }
    ))

    report = update["final_report"]
    assert "Old stale finding." not in report
    assert "Follow-up corrected finding." in report
    assert "Shared source (example.com)" in report


def test_final_report_backwards_compatibility_without_selected_report_findings():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Compat finding.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Compat source", "canonical_domain": "example.com"},
            ],
            "research_reviews": [{"sufficient": True, "selected_report_sources": [{"source_id": "S1", "status": "use", "reason": "ok"}]}],
        }
    ))

    report = update["final_report"]
    assert "Compat finding." in report
    assert "Compat source (example.com)" in report


def test_final_report_sources_render_clickable_links():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Linked finding.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {
                    "source_id": "S1",
                    "title": "Official launch post",
                    "url": "https://example.com/launch",
                    "normalized_url": "https://example.com/launch",
                    "canonical_domain": "example.com",
                }
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert "[1]" not in report
    assert "[Official launch post](https://example.com/launch)" in report


def test_final_report_top_sections_render_direct_source_urls(monkeypatch):
    from vanguard.report_generation import node as report_node
    from vanguard.report_generation.models import CitedText, ReportDraft, ReportSectionDraft, TeamSuggestionDraft, WhyItMattersDraft

    monkeypatch.setattr(
        report_node,
        "generate_report_draft",
        lambda *args, **kwargs: ReportDraft(
            executive_summary=ReportSectionDraft(
                paragraphs=[
                    CitedText(text="Summary claim one.", source_ids=["S1", "S2", "S3"]),
                    CitedText(text="Summary claim two.", source_ids=["S2"]),
                ]
            ),
            why_it_matters=WhyItMattersDraft(
                for_lance=[CitedText(text="Lance-specific why it matters.", source_ids=["S2"])],
                for_firm=[CitedText(text="Firm-wide why it matters.", source_ids=["S3"])],
            ),
            key_findings=ReportSectionDraft(
                cited_bullets=[CitedText(text="Trend bullet.", source_ids=["S1", "S3"])]
            ),
            team_suggestions=[
                TeamSuggestionDraft(
                    action="Run a focused pilot.",
                    owner_role="Spatial AI Lead",
                    pilot="Build a scoped prototype without links https://example.com/bad",
                    target_timing="4-6 weeks",
                    effort="M",
                    required_skills=["3D generation", "XR prototyping"],
                    dependencies="Tool access and sample scenes https://example.com/bad",
                    risk_and_mitigations="Risk of weak model output; mitigate with fixed prompts.",
                    success_metric="Reusable benchmark scorecard completed.",
                    related_technology="3D Gaussian Splatting",
                    source_ids=["S2", "S3"],
                )
            ],
        ),
    )

    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Finding backed by source one.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Source one", "url": "https://example.com/one", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Source two", "url": "https://example.com/two", "canonical_domain": "example.com"},
                {"source_id": "S3", "title": "Source three", "url": "https://example.com/three", "canonical_domain": "example.com"},
            ],
            "research_reviews": [{"sufficient": True, "selected_report_sources": [
                {"source_id": "S1", "status": "use", "reason": "ok"},
                {"source_id": "S2", "status": "use", "reason": "ok"},
                {"source_id": "S3", "status": "use", "reason": "ok"},
            ]}],
        }
    ))

    report = update["final_report"]
    assert "Summary claim one. Sources: https://example.com/one, https://example.com/two, https://example.com/three" in report
    assert "Summary claim two. Source: https://example.com/two" in report
    assert "### For the Selected Lance" in report
    assert "Lance-specific why it matters. Source: https://example.com/two" in report
    assert "### For the IT Consulting Firm" in report
    assert "Firm-wide why it matters. Source: https://example.com/three" in report
    assert "### Trend bullet" in report
    assert "Trend bullet. Sources: https://example.com/one, https://example.com/three" in report
    assert "### 1. Run a focused pilot." in report
    assert "| Owner role | Spatial AI Lead |" in report
    assert "https://example.com/bad" not in report
    assert "[1]" not in report
    assert re.search(r"\bS\d+\b", report) is None


def test_final_report_caps_urls_per_claim_and_keeps_sources_list_uncapped(monkeypatch):
    from vanguard.report_generation import node as report_node
    from vanguard.report_generation.models import CitedText, ReportDraft, ReportSectionDraft

    monkeypatch.setattr(
        report_node,
        "generate_report_draft",
        lambda *args, **kwargs: ReportDraft(
            executive_summary=ReportSectionDraft(
                paragraphs=[CitedText(text="Many-source claim.", source_ids=["S1", "S2", "S3", "S4"])]
            ),
        ),
    )
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": f"Finding {i}.", "source_ids": [f"S{i}"]}
                for i in range(1, 5)
            ],
            "research_sources": [
                {"source_id": f"S{i}", "title": f"Source {i}", "url": f"https://example.com/{i}", "canonical_domain": "example.com"}
                for i in range(1, 5)
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert "Many-source claim. Sources: https://example.com/1, https://example.com/2, https://example.com/3" in report
    assert "Many-source claim. Sources: https://example.com/1, https://example.com/2, https://example.com/3, https://example.com/4" not in report
    assert "[Source 4](https://example.com/4)" in report


def test_final_report_body_uses_direct_source_urls_not_numeric_citations():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Body cites source.", "source_ids": ["S1", "S2"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Source one", "url": "https://example.com/one", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Source two", "normalized_url": "https://example.com/two", "canonical_domain": "example.com"},
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert re.search(r"\[\d+\]", report) is None
    assert "Sources: https://example.com/one, https://example.com/two" in report


def test_final_report_uses_prose_first_rendering_for_analysis_sections(monkeypatch):
    from vanguard.report_generation import node as report_node
    from vanguard.report_generation.models import CitedText, ReportDraft, ReportSectionDraft

    monkeypatch.setattr(
        report_node,
        "generate_report_draft",
        lambda *args, **kwargs: ReportDraft(
            executive_summary=ReportSectionDraft(
                paragraphs=[CitedText(text="Summary paragraph with evidence.", source_ids=["S1"])]
            ),
            key_findings=ReportSectionDraft(
                cited_bullets=[
                    CitedText(text="Technology Alpha is maturing quickly. It matters for spatial workflows.", source_ids=["S1"]),
                    CitedText(text="Technology Beta remains earlier-stage. Evidence is narrower.", source_ids=["S2"]),
                ]
            ),
            limitations=ReportSectionDraft(
                paragraphs=[CitedText(text="Evidence is uneven across vendors.", source_ids=["S2"])]
            ),
        ),
    )
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Technology Alpha is maturing quickly.", "source_ids": ["S1"]},
                {"summary": "Technology Beta remains earlier-stage.", "source_ids": ["S2"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Alpha source", "url": "https://example.com/alpha", "canonical_domain": "example.com"},
                {"source_id": "S2", "title": "Beta source", "url": "https://example.com/beta", "canonical_domain": "example.com"},
            ],
            "research_reviews": [
                {
                    "sufficient": True,
                    "source_quality_assessment": "Primary coverage is good.",
                    "coverage_gaps": ["Benchmark coverage is thin."],
                }
            ],
            "source_diversity_notes": ["Most sources come from one domain."],
        }
    ))

    report = update["final_report"]
    trending = report.split("## Trending Technologies", 1)[1].split("## Team Suggestions", 1)[0]
    confidence = report.split("## Confidence and Gaps", 1)[1].split("## Selected Sources", 1)[0]

    assert "### Technology Alpha is maturing quickly" in trending
    assert "Technology Alpha is maturing quickly. It matters for spatial workflows. Source: https://example.com/alpha" in trending
    assert "### Technology Beta remains earlier-stage" in trending
    assert "\n- Technology Alpha" not in trending
    assert "\n- Technology Beta" not in trending
    assert "Primary coverage is good. Benchmark coverage is thin." in confidence
    assert "Most sources come from one domain." not in confidence
    assert "\n- Primary coverage" not in confidence
    assert "## Selected Sources" in report
    assert "- 1. [Alpha source](https://example.com/alpha)" in report


def test_final_report_marble_claim_uses_marble_and_worldact_urls_only():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Marble should use the Marble/WorldAct stack.", "source_ids": ["S1", "S2"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Marble docs", "url": "https://marble.example/docs", "canonical_domain": "marble.example"},
                {"source_id": "S2", "title": "WorldAct notes", "url": "https://worldact.example/notes", "canonical_domain": "worldact.example"},
                {"source_id": "S3", "title": "AWS unrelated", "url": "https://aws.example/ignored", "canonical_domain": "aws.example"},
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert "https://marble.example/docs" in report
    assert "https://worldact.example/notes" in report
    assert "https://aws.example/ignored" not in report


def test_final_report_sanitizes_internal_source_ids_from_body_text():
    update = final_report_generation(report_state(
        {
            "research_intent": "intent",
            "research_findings": [
                {"summary": "Finding mentions [S1][S2] and bare S3 internally.", "source_ids": ["S1"]},
            ],
            "research_sources": [
                {"source_id": "S1", "title": "Source one", "canonical_domain": "example.com"},
            ],
            "research_reviews": [{"sufficient": True}],
        }
    ))

    report = update["final_report"]
    assert re.search(r"\bS\d+\b", report) is None
    assert "Finding mentions" in report
    assert "[1]" not in report


def test_recorder_adds_lightweight_source_assessment_metadata():
    recorder = research.ResearchRunRecorder()

    recorded = recorder.record_search_results(
        [
            {
                "provider": "tavily",
                "query": "q",
                "url": "https://blogs.nvidia.com/",
                "title": "NVIDIA Blog",
                "summary": "Index page summary",
                "raw_content_path": None,
                "published_date": None,
                "normalized_url": "https://blogs.nvidia.com/",
                "canonical_domain": "blogs.nvidia.com",
            },
            {
                "provider": "exa",
                "query": "q",
                "url": "https://www.reuters.com/business/nvidia-example/",
                "title": "Reuters Nvidia report",
                "summary": "News summary",
                "raw_content_path": None,
                "published_date": "2026-05-07",
                "normalized_url": "https://reuters.com/business/nvidia-example",
                "canonical_domain": "reuters.com",
            },
        ],
        [],
    )

    index_source, news_source = recorded
    assert index_source["source_type"] == "index_or_feed"
    assert index_source["source_quality"] == "low"
    assert index_source["source_warnings"] == ["generic_index_page"]
    assert news_source["source_type"] == "source"
    assert news_source["source_quality"] == "high"
    assert news_source["source_warnings"] == []
