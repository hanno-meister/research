from __future__ import annotations

from datetime import date
from functools import lru_cache
import logging

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .graph import builder
from .langgraph_configuration import LangGraphConfig


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class ResearchRequest(BaseModel):
    human_message: str
    allowed_domains: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None


class ResearchResponse(BaseModel):
    final_report: str | None = None
    research_brief: str | None = None
    research_tasks: list[dict[str, object]] = Field(default_factory=list)
    research_findings: list[dict[str, object]] = Field(default_factory=list)
    research_sources: list[dict[str, object | None]] = Field(default_factory=list)
    evidence_artifacts: list[dict[str, object | None]] = Field(default_factory=list)
    research_reviews: list[dict[str, object]] = Field(default_factory=list)
    search_provider_counts: dict[str, int] = Field(default_factory=dict)
    search_domain_counts: dict[str, int] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_compiled_graph():
    return builder.compile()


def get_runtime_config() -> LangGraphConfig:
    return LangGraphConfig()


app = FastAPI(title="Vanguard Research API")


@app.post("/research", response_model=ResearchResponse)
async def run_research(
    request: ResearchRequest,
    graph=Depends(get_compiled_graph),
    runtime_config: LangGraphConfig = Depends(get_runtime_config),
) -> dict[str, object]:
    graph_input: dict[str, object] = {"research_intent": request.human_message}
    if request.allowed_domains is not None:
        graph_input["allowed_domains"] = request.allowed_domains
    if request.start_date is not None:
        graph_input["start_date"] = request.start_date
    if request.end_date is not None:
        graph_input["end_date"] = request.end_date

    return await graph.ainvoke(graph_input, context=runtime_config)
