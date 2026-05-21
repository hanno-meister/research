from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from vanguard.api import app, get_compiled_graph, get_runtime_config


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], object]] = []

    async def ainvoke(self, graph_input: dict[str, object], *, context: object):
        self.calls.append((graph_input, context))
        return {
            "final_report": "Final answer",
            "research_brief": "Research brief",
            "research_tasks": [{"task_id": "task-1", "description": "Task"}],
            "research_findings": [{"summary": "Finding", "source_ids": ["S1"]}],
            "research_sources": [{"source_id": "S1", "url": "https://example.com"}],
            "evidence_artifacts": [{"source_id": "S1", "path": "/evidence/source.md"}],
            "research_reviews": [{"sufficient": True}],
            "search_provider_counts": {"exa": 1},
            "search_domain_counts": {"example.com": 1},
        }


class CopyableRuntimeConfig:
    def __init__(self, evidence_root: Path | None = None) -> None:
        self.evidence_root = evidence_root

    def model_copy(self, *, update: dict[str, object]):
        evidence_root = update.get("evidence_root")
        return CopyableRuntimeConfig(evidence_root=evidence_root if isinstance(evidence_root, Path) else None)


class EvidenceRootCheckingGraph(FakeGraph):
    async def ainvoke(self, graph_input: dict[str, object], *, context: object):
        assert isinstance(context, CopyableRuntimeConfig)
        assert isinstance(context.evidence_root, Path)
        assert context.evidence_root.exists()
        return await super().ainvoke(graph_input, context=context)


class PartialGraph(FakeGraph):
    async def ainvoke(self, graph_input: dict[str, object], *, context: object):
        result = await super().ainvoke(graph_input, context=context)
        result["report_status"] = "partial"
        result["research_reviews"] = [{"sufficient": False}]
        return result


def test_research_endpoint_maps_request_to_graph_input():
    fake_graph = FakeGraph()
    fake_config = object()
    app.dependency_overrides[get_compiled_graph] = lambda: fake_graph
    app.dependency_overrides[get_runtime_config] = lambda: fake_config

    try:
        response = TestClient(app).post(
            "/research",
            json={
                "human_message": "Research LangGraph agents",
                "selected_lance": {
                    "id": "sdlpg",
                    "name": "Repository Context Graphs",
                    "description": "Use property graphs for agent context.",
                },
                "allowed_domains": ["langchain.com", "docs.langchain.com"],
                "start_date": "2026-01-01",
                "end_date": "2026-05-01",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "final_report": "Final answer",
        "status": "sufficient",
        "research_brief": "Research brief",
        "source_count": 1,
        "review_rounds": 1,
    }
    assert fake_graph.calls == [
        (
            {
                "research_intent": "Research LangGraph agents",
                "selected_lance": {
                    "id": "sdlpg",
                    "name": "Repository Context Graphs",
                    "description": "Use property graphs for agent context.",
                },
                "allowed_domains": ["langchain.com", "docs.langchain.com"],
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 5, 1),
            },
            fake_config,
        )
    ]


def test_research_endpoint_accepts_request_without_optional_constraints():
    fake_graph = FakeGraph()
    app.dependency_overrides[get_compiled_graph] = lambda: fake_graph
    app.dependency_overrides[get_runtime_config] = lambda: object()

    try:
        response = TestClient(app).post("/research", json={"human_message": "Summarize current AI search APIs"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_graph.calls[0][0] == {"research_intent": "Summarize current AI search APIs"}
    assert "debug" not in response.json()


def test_research_endpoint_verbose_response_includes_debug_state():
    fake_graph = FakeGraph()
    app.dependency_overrides[get_compiled_graph] = lambda: fake_graph
    app.dependency_overrides[get_runtime_config] = lambda: object()

    try:
        response = TestClient(app).post(
            "/research",
            json={"human_message": "Summarize current AI search APIs", "verbose": True},
        )
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "sufficient"
    assert body["debug"]["research_tasks"] == [{"task_id": "task-1", "description": "Task"}]
    assert body["debug"]["research_sources"] == [{"source_id": "S1", "url": "https://example.com"}]


def test_research_endpoint_prefers_report_status_partial():
    fake_graph = PartialGraph()
    app.dependency_overrides[get_compiled_graph] = lambda: fake_graph
    app.dependency_overrides[get_runtime_config] = lambda: object()

    try:
        response = TestClient(app).post("/research", json={"human_message": "Research partial report"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "partial"


def test_research_endpoint_uses_temporary_evidence_root_for_copyable_config():
    fake_graph = EvidenceRootCheckingGraph()
    app.dependency_overrides[get_compiled_graph] = lambda: fake_graph
    app.dependency_overrides[get_runtime_config] = lambda: CopyableRuntimeConfig()

    try:
        response = TestClient(app).post("/research", json={"human_message": "Research temporary storage"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    _graph_input, context = fake_graph.calls[0]
    assert isinstance(context, CopyableRuntimeConfig)
    assert isinstance(context.evidence_root, Path)
    assert not context.evidence_root.exists()
