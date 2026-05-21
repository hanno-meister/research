"""Optional LLM report drafting."""

from __future__ import annotations

import logging
from time import perf_counter

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .models import ReportDraft
from .prompts import FINAL_REPORT_PROMPT


logger = logging.getLogger(__name__)


def generate_report_draft(research_intent, selected_lance, report_bundle, runtime) -> ReportDraft:
    if runtime is None:
        return ReportDraft()
    start = perf_counter()
    try:
        logger.info(
            "Calling final report writer model",
            extra={
                "finding_count": len(report_bundle.get("findings", []) or []),
                "report_source_count": len(report_bundle.get("sources", []) or []),
            },
        )
        model = ChatOpenAI(
            model=runtime.context.large_model,
            base_url=runtime.context.openai_base_url,
            api_key=runtime.context.azure_openai_api_key,
            use_responses_api=False,
        ).with_structured_output(ReportDraft)
        prompt = FINAL_REPORT_PROMPT.format(
            research_intent=research_intent,
            selected_lance=selected_lance or "none",
            report_status=report_bundle.get("status", "incomplete"),
            bundle_findings=report_bundle.get("findings", []),
            bundle_sources=report_bundle.get("sources", []),
            required_topics=report_bundle.get("required_topics", []),
            coverage_gaps=report_bundle.get("coverage_gaps", []),
            contradiction_notes=report_bundle.get("contradiction_notes", []),
            methodology_caveats=report_bundle.get("methodology_caveats", []),
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
