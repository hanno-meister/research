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
    MAX_FOLLOW_UP_SEARCHES,
    MAX_FOLLOW_UP_WORKERS,
    MAX_REVIEW_ROUNDS,
)
from .evidence import read_selected_evidence
from .followup import follow_up_worker_tasks, run_follow_up_workers
from .models import EvidenceReadRequest, ResearchEvaluation
from .prompts import REVIEW_RESEARCH_PROMPT


logger = logging.getLogger(__name__)


async def review_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    """Evaluate research quality and run bounded targeted follow-up if needed."""

    if not state.get("research_brief"):
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    model = _review_model(runtime.context)
    backend = filesystem_backend_for_config(runtime.context)
    reviews: list[dict[str, object]] = []
    evidence_read_records: list[dict[str, str | int]] = []
    evidence_snippets: list[dict[str, str | int]] = []
    aggregate_update = _empty_update()
    workers_used = 0
    searches_used = 0
    evidence_reads_used = 0
    current_state: AgentState = dict(state)  # type: ignore[assignment]
    logger.info(
        "Starting research review",
        extra={
            "finding_count": len(state.get("research_findings", []) or []),
            "source_count": len(state.get("research_sources", []) or []),
            "evidence_artifact_count": len(state.get("evidence_artifacts", []) or []),
            "max_review_rounds": MAX_REVIEW_ROUNDS,
            "max_follow_up_workers": MAX_FOLLOW_UP_WORKERS,
            "max_follow_up_searches": MAX_FOLLOW_UP_SEARCHES,
            "max_evidence_reads": MAX_EVIDENCE_READS,
        },
    )

    for round_number in range(1, MAX_REVIEW_ROUNDS + 1):
        logger.info(
            "Starting review round",
            extra={
                "round": round_number,
                "finding_count": len(current_state.get("research_findings", []) or []),
                "source_count": len(current_state.get("research_sources", []) or []),
                "evidence_snippet_count": len(evidence_snippets),
            },
        )
        evaluation = await _evaluate(
            model,
            current_state,
            round_number=round_number,
            evidence_snippets=evidence_snippets,
        )
        requested_evidence = list(evaluation.evidence_to_read)

        logger.info(
            "Reading review-selected evidence",
            extra={
                "round": round_number,
                "requested_count": len(requested_evidence),
                "remaining_reads": MAX_EVIDENCE_READS - evidence_reads_used,
            },
        )
        round_reads, read_records = read_selected_evidence(
            current_state,
            evaluation.evidence_to_read,
            remaining_reads=MAX_EVIDENCE_READS - evidence_reads_used,
            backend=backend,
        )
        evidence_reads_used += len(round_reads)
        evidence_snippets.extend(round_reads)
        evidence_read_records.extend(read_records)
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
                current_state,
                round_number=round_number,
                evidence_snippets=evidence_snippets,
            )

        reviews.append(
            _review_record(
                round_number,
                evaluation,
                read_records,
                evidence_requested=requested_evidence,
            )
        )
        if evaluation.sufficient:
            break

        remaining_workers = MAX_FOLLOW_UP_WORKERS - workers_used
        remaining_searches = MAX_FOLLOW_UP_SEARCHES - searches_used
        searches_per_worker = max(1, remaining_searches)
        follow_up_tasks = follow_up_worker_tasks(
            evaluation.follow_up_tasks,
            current_state,
            remaining_workers=remaining_workers,
            remaining_workers_by_search_budget=remaining_searches // searches_per_worker,
        )
        if not follow_up_tasks:
            logger.info(
                "No follow-up workers scheduled",
                extra={
                    "round": round_number,
                    "proposed_follow_up_count": len(evaluation.follow_up_tasks),
                    "remaining_workers": remaining_workers,
                    "remaining_searches": remaining_searches,
                },
            )
            break

        follow_up_start = perf_counter()
        logger.info(
            "Starting follow-up research workers",
            extra={
                "round": round_number,
                "worker_count": len(follow_up_tasks),
                "searches_per_worker": searches_per_worker,
            },
        )
        follow_up_update, search_budget_used = await run_follow_up_workers(
            current_state,
            runtime,
            follow_up_tasks,
            max_search_calls_per_worker=searches_per_worker,
        )
        workers_used += len(follow_up_tasks)
        searches_used += search_budget_used
        logger.info(
            "Follow-up research workers completed",
            extra={
                "round": round_number,
                "worker_count": len(follow_up_tasks),
                "duration_seconds": round(perf_counter() - follow_up_start, 3),
                "finding_count": len(follow_up_update.get("research_findings", []) or []),
                "source_count": len(follow_up_update.get("research_sources", []) or []),
                "search_budget_used": search_budget_used,
            },
        )
        _merge_update(aggregate_update, follow_up_update)
        current_state = _state_with_update(current_state, follow_up_update)

    aggregate_update["research_reviews"] = reviews
    aggregate_update["evidence_read_records"] = evidence_read_records
    logger.info(
        "Research review completed",
        extra={
            "review_round_count": len(reviews),
            "evidence_read_count": len(evidence_read_records),
            "follow_up_workers_used": workers_used,
            "follow_up_search_budget_used": searches_used,
        },
    )
    return aggregate_update


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


def _empty_update() -> dict[str, Any]:
    return {
        "research_findings": [],
        "research_sources": [],
        "evidence_artifacts": [],
        "source_diversity_notes": [],
    }


def _merge_update(target: dict[str, Any], update: dict[str, Any]) -> None:
    for key in (
        "research_findings",
        "research_sources",
        "evidence_artifacts",
        "source_diversity_notes",
    ):
        target[key].extend(update.get(key, []))
    if "search_provider_counts" in update:
        target["search_provider_counts"] = update["search_provider_counts"]
    if "search_domain_counts" in update:
        target["search_domain_counts"] = update["search_domain_counts"]


def _state_with_update(state: AgentState, update: dict[str, Any]) -> AgentState:
    merged: dict[str, Any] = dict(state)
    for key in (
        "research_findings",
        "research_sources",
        "evidence_artifacts",
        "source_diversity_notes",
    ):
        merged[key] = list(merged.get(key, [])) + list(update.get(key, []))
    for key in ("search_provider_counts", "search_domain_counts"):
        if update.get(key):
            merged[key] = update[key]
    return merged  # type: ignore[return-value]
