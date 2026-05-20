"""LangGraph node for final report generation."""

from __future__ import annotations

import logging
from time import perf_counter

from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.state import AgentState

from .findings import usable_findings_from_review
from .rendering import render_complete_report, render_incomplete_report
from .source_policy import latest_review, report_sources_by_id
from .writer import generate_report_draft


logger = logging.getLogger(__name__)


def final_report_generation(state: AgentState, runtime: Runtime[LangGraphConfig] | None = None):
    start = perf_counter()
    review = latest_review(state)
    if not review or not review.get("sufficient"):
        report = render_incomplete_report(state, review)
        logger.info(
            "Final report generation completed",
            extra={
                "status": "incomplete",
                "duration_seconds": round(perf_counter() - start, 3),
                "report_characters": len(report),
            },
        )
        return {"final_report": report}

    logger.info(
        "Starting final report generation",
        extra={
            "status": "sufficient",
            "finding_count": len(state.get("research_findings", []) or []),
            "source_count": len(state.get("research_sources", []) or []),
        },
    )
    report_sources = report_sources_by_id(state, review)
    findings = usable_findings_from_review(state, review, report_sources)
    draft = generate_report_draft(state, review, findings, report_sources, runtime)
    report = render_complete_report(state, review, findings, report_sources, draft)
    logger.info(
        "Final report generation completed",
        extra={
            "status": "sufficient",
            "duration_seconds": round(perf_counter() - start, 3),
            "usable_finding_count": len(findings),
            "report_source_count": len(report_sources),
            "report_characters": len(report),
        },
    )
    return {"final_report": report}
