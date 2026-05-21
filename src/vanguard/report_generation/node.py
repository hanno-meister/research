"""LangGraph node for final report generation."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Literal

from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.state import AgentState

from .findings import usable_findings_from_review
from .source_policy import mentioned_source_ids
from .rendering import render_complete_report, render_incomplete_report
from .source_policy import latest_review, report_sources_by_id
from .writer import generate_report_draft


logger = logging.getLogger(__name__)


def final_report_generation(state: AgentState, runtime: Runtime[LangGraphConfig] | None = None):
    start = perf_counter()
    review = latest_review(state)
    if not review:
        report = render_incomplete_report(state, review)
        logger.info(
            "Final report generation completed",
            extra={
                "status": "incomplete",
                "duration_seconds": round(perf_counter() - start, 3),
                "report_characters": len(report),
            },
        )
        return {"final_report": report, "report_status": "incomplete"}

    report_sources = report_sources_by_id(state, review)
    findings = usable_findings_from_review(state, review, report_sources)
    report_status = _report_status(review, findings, report_sources)
    if report_status == "incomplete":
        report = render_incomplete_report(_state_without_banned_findings(state, review), review)
        logger.info(
            "Final report generation completed",
            extra={
                "status": report_status,
                "duration_seconds": round(perf_counter() - start, 3),
                "usable_finding_count": len(findings),
                "report_source_count": len(report_sources),
                "report_characters": len(report),
            },
        )
        return {"final_report": report, "report_status": report_status}

    logger.info(
        "Starting final report generation",
        extra={
            "status": report_status,
            "finding_count": len(state.get("research_findings", []) or []),
            "source_count": len(state.get("research_sources", []) or []),
        },
    )
    draft = generate_report_draft(state, review, findings, report_sources, runtime, report_status=report_status)
    report = render_complete_report(state, review, findings, report_sources, draft, report_status=report_status)
    logger.info(
        "Final report generation completed",
        extra={
            "status": report_status,
            "duration_seconds": round(perf_counter() - start, 3),
            "usable_finding_count": len(findings),
            "report_source_count": len(report_sources),
            "report_characters": len(report),
        },
    )
    return {"final_report": report, "report_status": report_status}


def _report_status(
    review: dict[str, object],
    findings: list[dict[str, object]],
    report_sources: dict[str, dict[str, object]],
) -> Literal["sufficient", "partial", "incomplete"]:
    if review.get("core_brief_answerable") is False:
        return "incomplete"
    if not findings:
        return "incomplete"
    if review.get("sufficient") is True:
        return "sufficient"
    if not report_sources:
        return "incomplete"
    if review.get("selected_report_sources") or review.get("selected_report_findings") or review.get("required_report_topics"):
        return "partial"
    return "incomplete"


def _state_without_banned_findings(state: AgentState, review: dict[str, object]) -> AgentState:
    contradiction_notes = review.get("contradiction_notes", [])
    weak_notes = review.get("weak_or_unsupported_findings", [])
    banned = mentioned_source_ids(
        (contradiction_notes if isinstance(contradiction_notes, list) else [])
        + (weak_notes if isinstance(weak_notes, list) else [])
    )
    if not banned:
        return state
    filtered = []
    for finding in state.get("research_findings", []) or []:
        if not isinstance(finding, dict):
            continue
        source_ids = finding.get("source_ids", [])
        if isinstance(source_ids, list) and any(sid in banned for sid in source_ids):
            continue
        filtered.append(finding)
    return {**state, "research_findings": filtered}
