"""LangGraph node for research review/evaluation."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.research.agent import filesystem_backend_for_config
from vanguard.report_generation.findings import findings_with_ids
from vanguard.state import AgentState

from .defaults import (
    MAX_EVIDENCE_READS,
    MAX_REVIEW_ROUNDS,
)
from .evidence import read_selected_evidence
from .models import EvidenceReadRequest, ResearchEvaluation
from .prompts import REVIEW_RESEARCH_PROMPT


logger = logging.getLogger(__name__)


async def review_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    """Evaluate research quality once and append a pure review record."""

    if not state.get("research_brief"):
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    model = _review_model(runtime.context)
    backend = filesystem_backend_for_config(runtime.context)
    evidence_snippets: list[dict[str, str | int]] = []
    round_number = int(state.get("review_round", 0) or 0) + 1
    logger.info(
        "Starting research review",
        extra={
            "round": round_number,
            "finding_count": len(state.get("research_findings", []) or []),
            "source_count": len(state.get("research_sources", []) or []),
            "evidence_artifact_count": len(state.get("evidence_artifacts", []) or []),
            "max_review_rounds": MAX_REVIEW_ROUNDS,
            "max_evidence_reads": MAX_EVIDENCE_READS,
        },
    )

    evaluation = await _evaluate(
        model,
        state,
        round_number=round_number,
        evidence_snippets=evidence_snippets,
    )
    requested_evidence = list(evaluation.evidence_to_read)

    logger.info(
        "Reading review-selected evidence",
        extra={
            "round": round_number,
            "requested_count": len(requested_evidence),
            "remaining_reads": MAX_EVIDENCE_READS,
        },
    )
    round_reads, read_records = read_selected_evidence(
        state,
        evaluation.evidence_to_read,
        remaining_reads=MAX_EVIDENCE_READS,
        backend=backend,
    )
    evidence_snippets.extend(round_reads)
    logger.info(
        "Review evidence reads completed",
        extra={
            "round": round_number,
            "read_count": len(round_reads),
            "total_characters": sum(
                int(read.get("content_characters", 0)) for read in round_reads
            ),
        },
    )

    if round_reads:
        logger.info("Re-evaluating research after evidence reads", extra={"round": round_number})
        evaluation = await _evaluate(
            model,
            state,
            round_number=round_number,
            evidence_snippets=evidence_snippets,
        )

    review_record = _review_record(
        round_number,
        evaluation,
        read_records,
        evidence_requested=requested_evidence,
    )
    update = {
        "research_reviews": [review_record],
        "evidence_read_records": read_records,
        "review_round": round_number,
    }
    logger.info(
        "Research review completed",
        extra={
            "round": round_number,
            "sufficient": evaluation.sufficient,
            "evidence_read_count": len(read_records),
            "follow_up_task_count": len(evaluation.follow_up_tasks),
        },
    )
    return update


def _review_model(config: LangGraphConfig):
    return ChatOpenAI(
        model=config.large_model,
        base_url=config.openai_base_url,
        api_key=config.azure_openai_api_key,
        use_responses_api=False,
    ).with_structured_output(ResearchEvaluation)


async def _evaluate(
    model,
    state: AgentState,
    *,
    round_number: int,
    evidence_snippets: list[dict[str, str | int]],
) -> ResearchEvaluation:
    start = perf_counter()
    logger.info(
        "Calling review model",
        extra={
            "round": round_number,
            "finding_count": len(state.get("research_findings", []) or []),
            "source_count": len(state.get("research_sources", []) or []),
            "evidence_snippet_count": len(evidence_snippets),
            "evidence_snippet_characters": sum(
                int(snippet.get("content_characters", 0)) for snippet in evidence_snippets
            ),
        },
    )
    response = await model.ainvoke(
        [
            HumanMessage(
                content=REVIEW_RESEARCH_PROMPT.format(
                    round_number=round_number,
                    research_brief=state.get("research_brief", ""),
                    research_tasks=state.get("research_tasks", []),
                    research_findings=findings_with_ids(state),
                    research_sources=state.get("research_sources", []),
                    evidence_artifacts=state.get("evidence_artifacts", []),
                    research_feasibility_notes=state.get("research_feasibility_notes", []),
                    source_diversity_notes=state.get("source_diversity_notes", []),
                    search_provider_counts=state.get("search_provider_counts", {}),
                    search_domain_counts=state.get("search_domain_counts", {}),
                    evidence_snippets=evidence_snippets,
                )
            )
        ]
    )
    if not isinstance(response, ResearchEvaluation):
        raise TypeError(f"Expected ResearchEvaluation, got {type(response).__name__}")
    logger.info(
        "Review model completed",
        extra={
            "round": round_number,
            "duration_seconds": round(perf_counter() - start, 3),
            "sufficient": response.sufficient,
            "evidence_request_count": len(response.evidence_to_read),
            "follow_up_task_count": len(response.follow_up_tasks),
            "selected_report_source_count": len(response.selected_report_sources),
            "contradiction_count": len(response.contradiction_notes),
            "weak_finding_count": len(response.weak_or_unsupported_findings),
        },
    )
    return response


def _review_record(
    round_number: int,
    evaluation: ResearchEvaluation,
    read_records: list[dict[str, str | int]],
    *,
    evidence_requested: list[EvidenceReadRequest] | None = None,
) -> dict[str, object]:
    requested = evidence_requested or evaluation.evidence_to_read
    return {
        "round": round_number,
        "sufficient": evaluation.sufficient,
        "core_brief_answerable": evaluation.core_brief_answerable,
        "coverage_assessment": evaluation.coverage_assessment,
        "source_quality_assessment": evaluation.source_quality_assessment,
        "contradiction_notes": evaluation.contradiction_notes,
        "weak_or_unsupported_findings": evaluation.weak_or_unsupported_findings,
        "required_report_topics": evaluation.required_report_topics,
        "coverage_gaps": evaluation.coverage_gaps,
        "evidence_requested": [request.model_dump() for request in requested],
        "evidence_read": read_records,
        "selected_report_sources": [
            source.model_dump() for source in evaluation.selected_report_sources
        ],
        "selected_report_findings": [
            finding.model_dump() for finding in evaluation.selected_report_findings
        ],
        "follow_up_tasks": [task.model_dump() for task in evaluation.follow_up_tasks],
    }
