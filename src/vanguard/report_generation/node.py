"""LangGraph node for final report generation."""

from __future__ import annotations

import logging
from time import perf_counter
from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.state import AgentState

from .rendering import render_complete_report, render_incomplete_report
from .writer import generate_report_draft


logger = logging.getLogger(__name__)


def final_report_generation(state: AgentState, runtime: Runtime[LangGraphConfig] | None = None):
    start = perf_counter()
    bundle = state.get("report_bundle") if isinstance(state.get("report_bundle"), dict) else None
    if not bundle:
        report = render_incomplete_report(state, None)
        logger.info(
            "Final report generation completed",
            extra={
                "status": "incomplete",
                "duration_seconds": round(perf_counter() - start, 3),
                "report_characters": len(report),
            },
        )
        return {"final_report": report, "report_status": "incomplete"}

    report_sources = _bundle_sources_by_id(bundle)
    findings = _bundle_findings(bundle)
    report_status = str(bundle.get("status") or "incomplete")
    if report_status == "incomplete":
        report = render_incomplete_report(_state_from_bundle(state, bundle), bundle)
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
            "finding_count": len(findings),
            "source_count": len(report_sources),
        },
    )
    draft = generate_report_draft(state.get("research_intent", ""), state.get("selected_lance") or "none", bundle, runtime)
    report = render_complete_report(_state_from_bundle(state, bundle), bundle, findings, report_sources, draft, report_status=report_status)
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


def _bundle_sources_by_id(bundle: dict[str, object]) -> dict[str, dict[str, object]]:
    sources: dict[str, dict[str, object]] = {}
    for source in bundle.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        sources[source_id] = {**metadata, **source}
    return sources


def _bundle_findings(bundle: dict[str, object]) -> list[dict[str, object]]:
    findings = []
    for finding in bundle.get("findings", []) or []:
        if not isinstance(finding, dict):
            continue
        findings.append({**finding, "summary": finding.get("content") or finding.get("summary"), "source_ids": finding.get("citation_source_ids", [])})
    return findings


def _state_from_bundle(state: AgentState, bundle: dict[str, object]) -> AgentState:
    bundled_findings = _bundle_findings(bundle)
    caveats = bundle.get("methodology_caveats", []) if isinstance(bundle.get("methodology_caveats"), list) else []
    has_dropped_finding = any(isinstance(caveat, dict) and str(caveat.get("type", "")).startswith("dropped_") for caveat in caveats)
    fallback_findings = [] if has_dropped_finding else state.get("research_findings", [])
    if has_dropped_finding and not bundled_findings:
        dropped_source_ids = {
            sid
            for caveat in caveats
            if isinstance(caveat, dict)
            for sid in caveat.get("source_ids", []) or []
            if isinstance(sid, str)
        }
        for finding in state.get("research_findings", []) or []:
            if not isinstance(finding, dict):
                continue
            source_ids = finding.get("source_ids", []) if isinstance(finding.get("source_ids"), list) else []
            if any(sid in dropped_source_ids for sid in source_ids):
                continue
            fallback_findings.append(finding)
    return {**state, "research_findings": bundled_findings or fallback_findings, "source_diversity_notes": []}
