"""LangGraph node for research review/evaluation."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.research.node import MAX_SEARCH_CALLS_PER_WORKER
from vanguard.state import AgentState

from .defaults import MAX_EVIDENCE_READS, MAX_FOLLOW_UP_SEARCHES, MAX_FOLLOW_UP_WORKERS, MAX_REVIEW_ROUNDS
from .evidence import read_selected_evidence
from .followup import follow_up_worker_tasks, run_follow_up_workers
from .models import EvidenceReadRequest, ResearchEvaluation
from .prompts import review_prompt


async def review_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    """Evaluate research quality and run bounded targeted follow-up if needed."""

    if not state.get("research_brief"):
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    model = _review_model(runtime.context)
    reviews: list[dict[str, object]] = []
    evidence_read_records: list[dict[str, str | int]] = []
    evidence_snippets: list[dict[str, str | int]] = []
    aggregate_update = _empty_update()
    workers_used = 0
    searches_used = 0
    evidence_reads_used = 0
    current_state: AgentState = dict(state)  # type: ignore[assignment]

    for round_number in range(1, MAX_REVIEW_ROUNDS + 1):
        evaluation = await _evaluate(
            model,
            current_state,
            round_number=round_number,
            evidence_snippets=evidence_snippets,
        )
        requested_evidence = list(evaluation.evidence_to_read)

        round_reads, read_records = read_selected_evidence(
            current_state,
            evaluation.evidence_to_read,
            remaining_reads=MAX_EVIDENCE_READS - evidence_reads_used,
        )
        evidence_reads_used += len(round_reads)
        evidence_snippets.extend(round_reads)
        evidence_read_records.extend(read_records)

        if round_reads:
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
        searches_per_worker = max(1, min(MAX_SEARCH_CALLS_PER_WORKER, remaining_searches))
        follow_up_tasks = follow_up_worker_tasks(
            evaluation.follow_up_tasks,
            current_state,
            remaining_workers=remaining_workers,
            remaining_workers_by_search_budget=remaining_searches // searches_per_worker,
        )
        if not follow_up_tasks:
            break

        follow_up_update, search_budget_used = await run_follow_up_workers(
            current_state,
            runtime,
            follow_up_tasks,
            max_search_calls_per_worker=searches_per_worker,
        )
        workers_used += len(follow_up_tasks)
        searches_used += search_budget_used
        _merge_update(aggregate_update, follow_up_update)
        current_state = _state_with_update(current_state, follow_up_update)

    aggregate_update["research_reviews"] = reviews
    aggregate_update["evidence_read_records"] = evidence_read_records
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
    response = await model.ainvoke(
        [
            HumanMessage(
                content=review_prompt(
                    state,
                    round_number=round_number,
                    evidence_snippets=evidence_snippets,
                )
            )
        ]
    )
    if not isinstance(response, ResearchEvaluation):
        raise TypeError(f"Expected ResearchEvaluation, got {type(response).__name__}")
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
        "coverage_assessment": evaluation.coverage_assessment,
        "source_quality_assessment": evaluation.source_quality_assessment,
        "contradiction_notes": evaluation.contradiction_notes,
        "weak_or_unsupported_findings": evaluation.weak_or_unsupported_findings,
        "evidence_requested": [request.model_dump() for request in requested],
        "evidence_read": read_records,
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
