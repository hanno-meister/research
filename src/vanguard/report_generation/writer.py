"""Optional LLM report drafting."""

from __future__ import annotations

import logging
from time import perf_counter

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from vanguard.state import AgentState

from .models import ReportDraft
from .prompts import FINAL_REPORT_PROMPT


logger = logging.getLogger(__name__)


def generate_report_draft(state: AgentState, review, findings, report_sources, runtime, *, report_status: str = "sufficient") -> ReportDraft:
    if runtime is None:
        return ReportDraft()
    start = perf_counter()
    try:
        logger.info(
            "Calling final report writer model",
            extra={
                "finding_count": len(findings),
                "report_source_count": len(report_sources),
            },
        )
        model = ChatOpenAI(
            model=runtime.context.large_model,
            base_url=runtime.context.openai_base_url,
            api_key=runtime.context.azure_openai_api_key,
            use_responses_api=False,
        ).with_structured_output(ReportDraft)
        prompt = FINAL_REPORT_PROMPT.format(
            research_intent=state.get("research_intent", ""),
            selected_lance=state.get("selected_lance") or "none",
            research_findings=findings,
            research_reviews=review,
            required_report_topics=review.get("required_report_topics", []) if isinstance(review, dict) else [],
            coverage_gaps=review.get("coverage_gaps", []) if isinstance(review, dict) else [],
            report_status=report_status,
            selected_report_sources=list(report_sources.values()),
        )
        response = model.invoke([HumanMessage(content=prompt)])
    except Exception as exc:
        raise RuntimeError("Final report draft generation failed") from exc
    valid_draft = isinstance(response, ReportDraft)
    logger.info(
        "Final report writer model completed",
        extra={
            "duration_seconds": round(perf_counter() - start, 3),
            "valid_draft": valid_draft,
        },
    )
    return response if valid_draft else ReportDraft()
