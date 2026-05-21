from __future__ import annotations

from datetime import date
from functools import lru_cache
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi import Body, Depends, FastAPI
from pydantic import BaseModel, Field

from .graph import builder
from .langgraph_configuration import LangGraphConfig


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


TREND_REPORT_EXAMPLE_MESSAGE = "Create a technical trend-scouting report about emerging world generation models for spatial computing. Focus on recent systems, benchmarks, capabilities, limitations, and practical scouting recommendations."

TREND_REPORT_EXAMPLE_DOMAINS = [
    "technologyreview.com",
    "deeplearning.ai/the-batch/",
    "theneurondaily.com",
    "arxiv.org",
    "tldr.tech",
    "microsoft.com/en-us/ai/blog/",
    "aws.amazon.com/blogs/aws/",
    "ai.meta.com/blog/",
    "machinelearning.apple.com/",
    "openai.com/news/research/",
    "blogs.nvidia.com/blog/",
    "deepmind.google/blog/",
    "tencent.com/en-us/articles/",
    "research.baidu.com/blog/",
    "turing.ac.uk/news",
    "greensoftware.foundation/articles/",
    "thequantuminsider.com/",
    "venturebeat.com/category/ai/",
]

TREND_REPORT_EXAMPLE_LANCE = {
    "id": "scwrd",
    "name": "Generative 3D World Models & Spatial Intelligence",
    "description": "Exploring and integrating emerging world generation models to create consistent, explorable 3D environments from multimodal inputs (text, images, gestures). This Lance focuses on evaluating, adapting, and integrating state-of-the-art world generation tools—like World Labs Marble, NVIDIA Cosmos, and text-to-3D platforms—into spatial computing workflows.",
}


class LanceContext(BaseModel):
    id: str
    name: str
    description: str


class ResearchRequest(BaseModel):
    human_message: str = Field(examples=[TREND_REPORT_EXAMPLE_MESSAGE])
    selected_lance: LanceContext | None = Field(default=None, examples=[TREND_REPORT_EXAMPLE_LANCE])
    allowed_domains: list[str] | None = Field(
        default=None,
        examples=[TREND_REPORT_EXAMPLE_DOMAINS],
    )
    start_date: date | None = None
    end_date: date | None = None
    verbose: bool = False


class ResearchResponse(BaseModel):
    final_report: str | None = None
    status: str
    research_brief: str | None = None
    source_count: int = 0
    review_rounds: int = 0
    debug: dict[str, object] | None = None


@lru_cache(maxsize=1)
def get_compiled_graph():
    return builder.compile()


def get_runtime_config() -> LangGraphConfig:
    return LangGraphConfig()


app = FastAPI(title="Vanguard Research API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse, response_model_exclude_none=True)
async def run_research(
    request: ResearchRequest = Body(
        openapi_examples={
            "trend_report": {
                "summary": "Trend report",
                "value": {
                    "human_message": TREND_REPORT_EXAMPLE_MESSAGE,
                    "selected_lance": TREND_REPORT_EXAMPLE_LANCE,
                    "allowed_domains": TREND_REPORT_EXAMPLE_DOMAINS,
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-20",
                    "verbose": False,
                },
            }
        }
    ),
    graph=Depends(get_compiled_graph),
    runtime_config: LangGraphConfig = Depends(get_runtime_config),
) -> ResearchResponse:
    start = perf_counter()
    graph_input: dict[str, object] = {"research_intent": request.human_message}
    if request.selected_lance is not None:
        graph_input["selected_lance"] = request.selected_lance.model_dump()
    if request.allowed_domains is not None:
        graph_input["allowed_domains"] = request.allowed_domains
    if request.start_date is not None:
        graph_input["start_date"] = request.start_date
    if request.end_date is not None:
        graph_input["end_date"] = request.end_date

    logger.info(
        "API research request started",
        extra={
            "allowed_domain_count": len(request.allowed_domains or []),
            "selected_lance_id": request.selected_lance.id if request.selected_lance else None,
            "start_date": request.start_date.isoformat() if request.start_date else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
            "verbose": request.verbose,
        },
    )
    try:
        with TemporaryDirectory(prefix="vanguard-evidence-") as evidence_dir:
            result = await graph.ainvoke(
                graph_input,
                context=_runtime_config_with_evidence_root(runtime_config, Path(evidence_dir)),
            )
    except Exception:
        logger.exception(
            "API research request failed",
            extra={"duration_seconds": round(perf_counter() - start, 3)},
        )
        raise

    response = ResearchResponse(
        final_report=result.get("final_report") if isinstance(result.get("final_report"), str) else None,
        status=_research_status(result),
        research_brief=result.get("research_brief") if isinstance(result.get("research_brief"), str) else None,
        source_count=_count_dicts(result.get("research_sources")),
        review_rounds=_count_dicts(result.get("research_reviews")),
        debug=result if request.verbose else None,
    )
    logger.info(
        "API research request completed",
        extra={
            "duration_seconds": round(perf_counter() - start, 3),
            "status": response.status,
            "source_count": response.source_count,
            "review_rounds": response.review_rounds,
            "final_report_characters": len(response.final_report or ""),
        },
    )
    return response


def _research_status(result: dict[str, object]) -> str:
    report_status = result.get("report_status")
    if report_status in {"sufficient", "partial", "incomplete"}:
        return str(report_status)
    reviews = result.get("research_reviews")
    if not isinstance(reviews, list) or not reviews:
        return "unreviewed"
    latest_review = reviews[-1]
    if not isinstance(latest_review, dict):
        return "unreviewed"
    return "sufficient" if latest_review.get("sufficient") is True else "insufficient"


def _runtime_config_with_evidence_root(runtime_config: LangGraphConfig, evidence_root: Path):
    if hasattr(runtime_config, "model_copy"):
        return runtime_config.model_copy(update={"evidence_root": evidence_root})
    return runtime_config


def _count_dicts(value: object) -> int:
    if not isinstance(value, list):
        return 0
    return len([item for item in value if isinstance(item, dict)])
