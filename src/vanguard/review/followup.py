"""Bounded follow-up research execution for review."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.contracts import ResearchTask
from vanguard.planning import _sanitized_tasks
from vanguard.research.agent import create_research_agent, filesystem_backend_for_config
from vanguard.research.models import ResearchAgentOutput, ResearchSearchBudget
from vanguard.research.node import (
    ResearchWorkerTask,
    _agent_input,
    _allowed_domains_from_state,
    _state_update_from_parts,
    _structured_findings,
    _task_default_query,
    _task_highlight_query,
    _worker_task_from_mapping,
)
from vanguard.research.policy import search_context_from_state
from vanguard.research.recorder import ResearchRunRecorder
from vanguard.research.defaults import FOLLOW_UP_SEARCH_RESULTS_PER_PROVIDER
from vanguard.state import AgentState

from .defaults import MAX_FOLLOW_UP_SEARCHES, MAX_FOLLOW_UP_WORKERS


logger = logging.getLogger(__name__)


async def repair_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    """Run latest-review follow-up tasks as a dedicated repair node."""

    review_record = _latest_review(state)
    if not review_record:
        raise ValueError("Missing research review. Did review_research run?")

    review_round = int(review_record.get("round") or state.get("review_round", 0) or 0)
    proposed_tasks = _review_follow_up_tasks(review_record)
    searches_per_worker = max(1, MAX_FOLLOW_UP_SEARCHES)
    tasks = follow_up_worker_tasks(
        proposed_tasks,
        state,
        remaining_workers=MAX_FOLLOW_UP_WORKERS,
        remaining_workers_by_search_budget=MAX_FOLLOW_UP_SEARCHES // searches_per_worker,
    )
    logger.info(
        "Starting research repair",
        extra={
            "review_round": review_round,
            "proposed_follow_up_count": len(proposed_tasks),
            "worker_count": len(tasks),
            "searches_per_worker": searches_per_worker,
        },
    )
    if not tasks:
        return {
            "repair_logs": [
                _repair_log(
                    review_round=review_round,
                    tasks_requested=[_task_id(task, index) for index, task in enumerate(proposed_tasks, start=1)],
                    tasks_run=[],
                    tasks_succeeded=[],
                    tasks_failed=[],
                    update={},
                    source_diversity_notes=[],
                    search_budget_used=0,
                    duration_seconds=0.0,
                )
            ]
        }

    start = perf_counter()
    update, search_budget_used, task_failures = await run_follow_up_workers(
        state,
        runtime,
        tasks,
        max_search_calls_per_worker=searches_per_worker,
        produced_by=f"repair_research:round-{review_round}",
    )
    duration_seconds = round(perf_counter() - start, 3)
    successful_task_ids = _successful_task_ids(update.get("follow_up_results", []))
    repair_log = _repair_log(
        review_round=review_round,
        tasks_requested=[task.id for task in tasks],
        tasks_run=[task.id for task in tasks],
        tasks_succeeded=successful_task_ids,
        tasks_failed=task_failures,
        update=update,
        source_diversity_notes=_repair_source_diversity_notes(update.get("follow_up_results", [])),
        search_budget_used=search_budget_used,
        duration_seconds=duration_seconds,
    )
    logger.info(
        "Research repair completed",
        extra={
            "review_round": review_round,
            "worker_count": len(tasks),
            "succeeded_count": len(successful_task_ids),
            "failed_count": len(task_failures),
            "finding_count": len(update.get("research_findings", []) or []),
            "source_count": len(update.get("research_sources", []) or []),
            "search_budget_used": search_budget_used,
            "duration_seconds": duration_seconds,
        },
    )
    return {
        "research_findings": update.get("research_findings", []),
        "research_sources": update.get("research_sources", []),
        "evidence_artifacts": update.get("evidence_artifacts", []),
        "repair_logs": [repair_log],
        "search_provider_counts": update.get("search_provider_counts", state.get("search_provider_counts", {})),
        "search_domain_counts": update.get("search_domain_counts", state.get("search_domain_counts", {})),
    }


def follow_up_worker_tasks(
    tasks: list[ResearchTask],
    state: AgentState,
    *,
    remaining_workers: int,
    remaining_workers_by_search_budget: int,
) -> list[ResearchWorkerTask]:
    if remaining_workers <= 0 or remaining_workers_by_search_budget <= 0:
        return []

    allowed_domains = _allowed_domains_from_state(state)
    valid_tasks = [task for task in tasks if task.objective.strip()]
    task_limit = min(remaining_workers, remaining_workers_by_search_budget, len(valid_tasks))
    if task_limit <= 0:
        return []
    sanitized = _sanitized_tasks(
        valid_tasks[:task_limit],
        state,
        state.get("research_brief", ""),
        id_prefix="follow-up",
    )
    return [
        _worker_task_from_mapping(task.model_dump(), index, allowed_domains)
        for index, task in enumerate(sanitized, start=1)
    ]

async def run_follow_up_workers(
    state: AgentState,
    runtime: Runtime[LangGraphConfig],
    tasks: list[ResearchWorkerTask],
    *,
    max_search_calls_per_worker: int,
    produced_by: str | None = None,
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    backend = filesystem_backend_for_config(runtime.context)
    recorder = ResearchRunRecorder.from_existing_records(
        state.get("research_sources", []),
        state.get("evidence_artifacts", []),
    )
    agent = create_research_agent(runtime.context, backend=backend)
    research_brief = state.get("research_brief", "")
    worker_outputs = await asyncio.gather(
        *(
            run_research_worker_with_budget(
                agent=agent,
                state=state,
                research_brief=research_brief,
                task=task,
                backend=backend,
                recorder=recorder,
                max_search_calls=max_search_calls_per_worker,
            )
            for task in tasks
        ),
        return_exceptions=True,
    )

    findings = []
    follow_up_results = []
    task_failures: list[dict[str, str]] = []
    for task, output in zip(tasks, worker_outputs, strict=True):
        if isinstance(output, Exception):
            task_failures.append(
                {
                    "task_id": task.id,
                    "error_type": type(output).__name__,
                    "message": str(output),
                }
            )
            continue
        if not isinstance(output, ResearchAgentOutput):
            task_failures.append(
                {
                    "task_id": task.id,
                    "error_type": type(output).__name__,
                    "message": "Unexpected follow-up worker output.",
                }
            )
            continue
        task_findings = _structured_findings(output.findings, task, recorder)
        if produced_by:
            task_findings = [
                {
                    **finding,
                    "produced_by": produced_by,
                    "repair_task_id": task.id,
                }
                for finding in task_findings
            ]
        task_sources = recorder.new_sources()
        if produced_by:
            task_sources = [
                {
                    **source,
                    "produced_by": produced_by,
                    "repair_task_id": task.id,
                }
                for source in task_sources
            ]
        task_evidence_artifacts = recorder.new_evidence_artifacts()
        task_diversity_notes = list(output.source_diversity_notes)
        task_provider_counts = recorder.provider_counts()
        task_domain_counts = recorder.domain_counts()
        follow_up_results.append(
            {
                "task_id": task.id,
                "research_findings": task_findings,
                "research_sources": task_sources,
                "evidence_artifacts": task_evidence_artifacts,
                "source_diversity_notes": task_diversity_notes,
                "search_provider_counts": task_provider_counts,
                "search_domain_counts": task_domain_counts,
            }
        )
        findings.extend(task_findings)
    update = _state_update_from_parts(
        findings,
        [],
        recorder,
        new_only=True,
    )
    if produced_by:
        update["research_sources"] = [
            {
                **source,
                "produced_by": produced_by,
                "repair_task_id": _repair_task_id_for_source(source, follow_up_results),
            }
            for source in update.get("research_sources", [])
            if isinstance(source, dict)
        ]
    update["source_diversity_notes"] = []
    update["follow_up_results"] = follow_up_results
    return update, len(tasks) * max_search_calls_per_worker, task_failures


def _repair_task_id_for_source(source: dict[str, Any], follow_up_results: list[dict[str, Any]]) -> str:
    source_id = source.get("source_id")
    for result in follow_up_results:
        for result_source in result.get("research_sources", []) or []:
            if isinstance(result_source, dict) and result_source.get("source_id") == source_id:
                task_id = result.get("task_id")
                return task_id if isinstance(task_id, str) else ""
    return ""


def _latest_review(state: AgentState) -> dict[str, Any] | None:
    reviews = [review for review in state.get("research_reviews", []) or [] if isinstance(review, dict)]
    return reviews[-1] if reviews else None


def _review_follow_up_tasks(review_record: dict[str, Any]) -> list[ResearchTask]:
    tasks = []
    for item in review_record.get("follow_up_tasks", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            tasks.append(ResearchTask.model_validate(item))
        except Exception:
            continue
    return tasks


def _task_id(task: ResearchTask, index: int) -> str:
    return task.id.strip() or f"follow-up-{index}"


def _successful_task_ids(follow_up_results: object) -> list[str]:
    if not isinstance(follow_up_results, list):
        return []
    return [
        task_id
        for result in follow_up_results
        if isinstance(result, dict)
        if isinstance(task_id := result.get("task_id"), str)
    ]


def _repair_source_diversity_notes(follow_up_results: object) -> list[str]:
    if not isinstance(follow_up_results, list):
        return []
    notes: list[str] = []
    for result in follow_up_results:
        if not isinstance(result, dict):
            continue
        for note in result.get("source_diversity_notes", []) or []:
            if isinstance(note, str) and note.strip():
                notes.append(note.strip())
    return notes


def _repair_log(
    *,
    review_round: int,
    tasks_requested: list[str],
    tasks_run: list[str],
    tasks_succeeded: list[str],
    tasks_failed: list[dict[str, str]],
    update: dict[str, Any],
    source_diversity_notes: list[str],
    search_budget_used: int,
    duration_seconds: float,
) -> dict[str, Any]:
    return {
        "round": review_round,
        "triggered_by_review_round": review_round,
        "tasks_requested": tasks_requested,
        "tasks_run": tasks_run,
        "tasks_succeeded": tasks_succeeded,
        "tasks_failed": tasks_failed,
        "produced_finding_ids": [],
        "produced_source_ids": [
            source_id
            for source in update.get("research_sources", []) or []
            if isinstance(source, dict)
            if isinstance(source_id := source.get("source_id"), str)
        ],
        "produced_finding_count": len(update.get("research_findings", []) or []),
        "produced_source_count": len(update.get("research_sources", []) or []),
        "source_diversity_notes": source_diversity_notes,
        "search_provider_counts": update.get("search_provider_counts", {}),
        "search_domain_counts": update.get("search_domain_counts", {}),
        "search_budget_used": search_budget_used,
        "duration_seconds": duration_seconds,
    }


async def run_research_worker_with_budget(
    *,
    agent,
    state: AgentState,
    research_brief: str,
    task: ResearchWorkerTask,
    backend,
    recorder: ResearchRunRecorder,
    max_search_calls: int,
) -> ResearchAgentOutput:
    agent_context = search_context_from_state(
        state,
        research_brief,
        backend,
        recorder,
        default_query=_task_default_query(task, state, research_brief),
        default_highlight_query=_task_highlight_query(task, research_brief),
        focused_domains=task.focused_domains,
        task_id=task.id,
        search_budget=ResearchSearchBudget(max_search_calls=max_search_calls),
        results_per_provider=FOLLOW_UP_SEARCH_RESULTS_PER_PROVIDER,
    )
    search_attempts_before = recorder.search_attempts
    agent_result = await agent.ainvoke(
        _agent_input(research_brief, task, search_call_budget=max_search_calls),
        context=agent_context,
    )
    if recorder.search_attempts == search_attempts_before:
        raise ValueError(f"Research worker {task.id} completed without calling search_gateway")
    output = agent_result.get("structured_response")
    if not isinstance(output, ResearchAgentOutput):
        raise TypeError(f"Expected ResearchAgentOutput, got {type(output).__name__}")
    return output
