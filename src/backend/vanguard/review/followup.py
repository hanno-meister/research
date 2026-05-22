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
    _state_with_update,
    _structured_findings,
    _task_default_query,
    _task_highlight_query,
    _topological_task_batches,
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
    raw_follow_up_tasks = review_record.get("follow_up_tasks", []) or []
    tasks_requested = _requested_task_ids(raw_follow_up_tasks)
    proposed_tasks, invalid_task_drops = _review_follow_up_tasks_with_drops(raw_follow_up_tasks)
    tasks, scheduling_drops = follow_up_worker_tasks_with_drops(
        proposed_tasks,
        state,
        remaining_workers=MAX_FOLLOW_UP_WORKERS,
    )
    if len(tasks) > MAX_FOLLOW_UP_SEARCHES:
        scheduling_drops.extend(
            {"task_id": task.id, "reason": "dropped_search_cap"}
            for task in tasks[MAX_FOLLOW_UP_SEARCHES:]
        )
        tasks = tasks[:MAX_FOLLOW_UP_SEARCHES]
    # MAX_FOLLOW_UP_SEARCHES is a per-round cap; divide it across scheduled workers.
    searches_per_worker = max(1, MAX_FOLLOW_UP_SEARCHES // max(1, len(tasks)))
    tasks_dropped = invalid_task_drops + scheduling_drops
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
                    tasks_requested=tasks_requested,
                    tasks_run=[],
                    tasks_succeeded=[],
                    tasks_failed=[],
                    tasks_dropped=tasks_dropped,
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
        tasks_requested=tasks_requested,
        tasks_run=[task.id for task in tasks],
        tasks_succeeded=successful_task_ids,
        tasks_failed=task_failures,
        tasks_dropped=tasks_dropped,
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
            "dropped_count": len(tasks_dropped),
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
    remaining_workers_by_search_budget: int | None = None,
) -> list[ResearchWorkerTask]:
    worker_tasks, _drops = follow_up_worker_tasks_with_drops(
        tasks,
        state,
        remaining_workers=remaining_workers,
    )
    return worker_tasks


def follow_up_worker_tasks_with_drops(
    tasks: list[ResearchTask],
    state: AgentState,
    *,
    remaining_workers: int,
) -> tuple[list[ResearchWorkerTask], list[dict[str, str]]]:
    task_ids_by_review_id = {
        _task_id(task, index): f"follow-up-{index}"
        for index, task in enumerate(tasks, start=1)
    }
    if remaining_workers <= 0:
        return [], [
            _task_drop(task, index, "dropped_worker_cap", task_ids_by_review_id)
            for index, task in enumerate(tasks, start=1)
        ]

    allowed_domains = _allowed_domains_from_state(state)
    valid_tasks = []
    dropped_tasks = []
    for index, task in enumerate(tasks, start=1):
        if task.objective.strip():
            valid_tasks.append(task)
        else:
            dropped_tasks.append(_task_drop(task, index, "dropped_empty_objective", task_ids_by_review_id))
    task_limit = min(remaining_workers, len(valid_tasks))
    if task_limit <= 0:
        dropped_tasks.extend(
            _task_drop(task, index, "dropped_worker_cap", task_ids_by_review_id)
            for index, task in enumerate(valid_tasks, start=1)
        )
        return [], dropped_tasks
    scheduled_tasks = valid_tasks[:task_limit]
    dropped_tasks.extend(
        _task_drop(task, index, "dropped_worker_cap", task_ids_by_review_id)
        for index, task in enumerate(valid_tasks[task_limit:], start=task_limit + 1)
    )
    sanitized = _sanitized_tasks(
        scheduled_tasks,
        state,
        state.get("research_brief", ""),
        id_prefix="follow-up",
    )
    worker_tasks = [
        _worker_task_from_mapping(task.model_dump(), index, allowed_domains)
        for index, task in enumerate(sanitized, start=1)
    ]
    worker_tasks = [
        _with_follow_up_dependency_ids(task, task_ids_by_review_id)
        for task in worker_tasks
    ]
    runnable_tasks, dependency_drops = _drop_unrunnable_dependency_tasks(worker_tasks)
    dropped_tasks.extend(dependency_drops)
    try:
        _topological_task_batches(runnable_tasks)
    except ValueError as exc:
        reason = _dependency_drop_reason(str(exc))
        return [], dropped_tasks + [
            {"task_id": task.id, "reason": reason, "message": str(exc)}
            for task in runnable_tasks
        ]
    return runnable_tasks, dropped_tasks

async def run_follow_up_workers(
    state: AgentState,
    runtime: Runtime[LangGraphConfig],
    tasks: list[ResearchWorkerTask],
    *,
    max_search_calls_per_worker: int,
    produced_by: str | None = None,
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    backend = filesystem_backend_for_config(runtime.context)
    agent = create_research_agent(runtime.context, backend=backend)
    research_brief = state.get("research_brief", "")

    findings = []
    follow_up_results = []
    task_failures: list[dict[str, str]] = []
    search_budget_used = 0
    current_state: AgentState = dict(state)  # type: ignore[assignment]
    for batch in _topological_task_batches(tasks):
        worker_outputs = await asyncio.gather(
            *(
                _run_single_follow_up_worker(
                    agent=agent,
                    state=current_state,
                    research_brief=research_brief,
                    task=task,
                    backend=backend,
                    max_search_calls=max_search_calls_per_worker,
                    produced_by=produced_by,
                )
                for task in batch
            ),
            return_exceptions=True,
        )
        batch_findings = []
        batch_sources = []
        batch_artifacts = []
        for task, output in zip(batch, worker_outputs, strict=True):
            if isinstance(output, Exception):
                task_failures.append(
                    {
                        "task_id": task.id,
                        "error_type": type(output).__name__,
                        "message": str(output),
                    }
                )
                continue
            if not isinstance(output, dict):
                task_failures.append(
                    {
                        "task_id": task.id,
                        "error_type": type(output).__name__,
                        "message": "Unexpected follow-up worker output.",
                    }
                )
                continue
            follow_up_results.append(output)
            task_findings = output.get("research_findings", []) or []
            findings.extend(task_findings)
            batch_findings.extend(task_findings)
            batch_sources.extend(output.get("research_sources", []) or [])
            batch_artifacts.extend(output.get("evidence_artifacts", []) or [])
            search_budget_used += int(output.get("search_budget_used", 0) or 0)
        current_state = _state_with_update(
            current_state,
            {
                "research_findings": batch_findings,
                "research_sources": batch_sources,
                "evidence_artifacts": batch_artifacts,
            },
        )
    _dedupe_source_ids(follow_up_results, state.get("research_sources", []) or [])
    findings = [
        finding
        for result in follow_up_results
        for finding in result.get("research_findings", []) or []
        if isinstance(finding, dict)
    ]
    update = _merge_follow_up_results(follow_up_results, findings)
    update["source_diversity_notes"] = []
    update["follow_up_results"] = follow_up_results
    return update, search_budget_used, task_failures


def _latest_review(state: AgentState) -> dict[str, Any] | None:
    reviews = [review for review in state.get("research_reviews", []) or [] if isinstance(review, dict)]
    return reviews[-1] if reviews else None


def _review_follow_up_tasks(review_record: dict[str, Any]) -> list[ResearchTask]:
    tasks, _drops = _review_follow_up_tasks_with_drops(review_record.get("follow_up_tasks", []) or [])
    return tasks


def _review_follow_up_tasks_with_drops(raw_tasks: list[Any]) -> tuple[list[ResearchTask], list[dict[str, str]]]:
    tasks = []
    drops = []
    for index, item in enumerate(raw_tasks, start=1):
        if not isinstance(item, dict):
            drops.append({"task_id": f"follow-up-{index}", "reason": "dropped_invalid_task"})
            continue
        try:
            tasks.append(ResearchTask.model_validate(item))
        except Exception as exc:
            drops.append({"task_id": _raw_task_id(item, index), "reason": "dropped_invalid_task", "message": str(exc)})
            continue
    return tasks, drops


def _requested_task_ids(raw_tasks: list[Any]) -> list[str]:
    return [_raw_task_id(item, index) for index, item in enumerate(raw_tasks, start=1)]


def _raw_task_id(item: Any, index: int) -> str:
    if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
        return item["id"].strip()
    return f"follow-up-{index}"


def _task_id(task: ResearchTask, index: int) -> str:
    return task.id.strip() or f"follow-up-{index}"


def _task_drop(
    task: ResearchTask,
    index: int,
    reason: str,
    task_ids_by_review_id: dict[str, str] | None = None,
) -> dict[str, str]:
    task_id = _task_id(task, index)
    if task_ids_by_review_id:
        task_id = task_ids_by_review_id.get(task_id, task_id)
    return {"task_id": task_id, "reason": reason}


def _with_follow_up_dependency_ids(
    task: ResearchWorkerTask,
    task_ids_by_review_id: dict[str, str],
) -> ResearchWorkerTask:
    depends_on = tuple(
        task_ids_by_review_id.get(dependency, dependency)
        for dependency in task.depends_on
    )
    return ResearchWorkerTask(
        id=task.id,
        objective=task.objective,
        boundaries=task.boundaries,
        key_questions=task.key_questions,
        target_terms=task.target_terms,
        focused_domains=task.focused_domains,
        depends_on=depends_on,
        expected_output=task.expected_output,
        effort=task.effort,
    )


def _dependency_drop_reason(message: str) -> str:
    if "cycle" in message.lower():
        return "dropped_cycle"
    return "dropped_unresolved_dependency"


def _drop_unrunnable_dependency_tasks(
    tasks: list[ResearchWorkerTask],
) -> tuple[list[ResearchWorkerTask], list[dict[str, str]]]:
    remaining = list(tasks)
    dropped: list[dict[str, str]] = []
    while True:
        task_ids = {task.id for task in remaining}
        blocked = [
            task
            for task in remaining
            if any(dependency not in task_ids for dependency in task.depends_on)
        ]
        if not blocked:
            return remaining, dropped
        blocked_ids = {task.id for task in blocked}
        dropped.extend(
            {"task_id": task.id, "reason": "dropped_unresolved_dependency"}
            for task in blocked
        )
        remaining = [task for task in remaining if task.id not in blocked_ids]


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
    tasks_dropped: list[dict[str, str]],
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
        "tasks_dropped": tasks_dropped,
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


async def _run_single_follow_up_worker(
    *,
    agent,
    state: AgentState,
    research_brief: str,
    task: ResearchWorkerTask,
    backend,
    max_search_calls: int,
    produced_by: str | None,
) -> dict[str, Any]:
    recorder = ResearchRunRecorder.from_existing_records(
        state.get("research_sources", []),
        state.get("evidence_artifacts", []),
    )
    output = await run_research_worker_with_budget(
        agent=agent,
        state=state,
        research_brief=research_brief,
        task=task,
        backend=backend,
        recorder=recorder,
        max_search_calls=max_search_calls,
    )
    task_findings = _structured_findings(output.findings, task, recorder)
    task_sources = recorder.new_sources()
    if produced_by:
        task_findings = [
            {**finding, "produced_by": produced_by, "repair_task_id": task.id}
            for finding in task_findings
        ]
        task_sources = [
            {**source, "produced_by": produced_by, "repair_task_id": task.id}
            for source in task_sources
        ]
    return {
        "task_id": task.id,
        "research_findings": task_findings,
        "research_sources": task_sources,
        "evidence_artifacts": recorder.new_evidence_artifacts(),
        "source_diversity_notes": list(output.source_diversity_notes),
        "search_provider_counts": recorder.provider_counts(),
        "search_domain_counts": recorder.domain_counts(),
        "search_budget_used": recorder.search_attempts,
    }


def _merge_follow_up_results(
    follow_up_results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    sources_by_key: dict[str, dict[str, Any]] = {}
    artifacts_by_path: dict[str, dict[str, Any]] = {}
    provider_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for result in follow_up_results:
        for source in result.get("research_sources", []) or []:
            if not isinstance(source, dict):
                continue
            key = source.get("normalized_url") or source.get("url") or source.get("source_id")
            if isinstance(key, str) and key:
                sources_by_key.setdefault(key, source)
        for artifact in result.get("evidence_artifacts", []) or []:
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("path")
            if isinstance(path, str) and path:
                artifacts_by_path.setdefault(path, artifact)
        _add_counts(provider_counts, result.get("search_provider_counts", {}))
        _add_counts(domain_counts, result.get("search_domain_counts", {}))
    return {
        "research_findings": findings,
        "research_sources": list(sources_by_key.values()),
        "evidence_artifacts": list(artifacts_by_path.values()),
        "search_provider_counts": provider_counts,
        "search_domain_counts": domain_counts,
    }


def _dedupe_source_ids(follow_up_results: list[dict[str, Any]], existing_sources: list[Any]) -> None:
    source_keys_by_id: dict[str, str] = {
        source_id: _source_identity_key(source)
        for source in existing_sources
        if isinstance(source, dict)
        if isinstance(source_id := source.get("source_id"), str) and source_id
    }
    used_source_ids = {
        source_id
        for source in existing_sources
        if isinstance(source, dict)
        if isinstance(source_id := source.get("source_id"), str) and source_id
    } | {
        source_id
        for result in follow_up_results
        for source in result.get("research_sources", []) or []
        if isinstance(source, dict)
        if isinstance(source_id := source.get("source_id"), str) and source_id
    }
    next_source_number = _next_source_number(used_source_ids)
    for result in follow_up_results:
        remapped_ids: dict[str, str] = {}
        for source in result.get("research_sources", []) or []:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                continue
            source_key = _source_identity_key(source)
            existing_key = source_keys_by_id.get(source_id)
            if existing_key is None or existing_key == source_key:
                source_keys_by_id[source_id] = source_key
                continue
            new_source_id = _next_unique_source_id(used_source_ids, next_source_number)
            next_source_number = int(new_source_id.removeprefix("S")) + 1
            source["source_id"] = new_source_id
            remapped_ids[source_id] = new_source_id
            source_keys_by_id[new_source_id] = source_key
        if remapped_ids:
            _remap_finding_source_ids(result.get("research_findings", []), remapped_ids)


def _source_identity_key(source: dict[str, Any]) -> str:
    key = source.get("normalized_url") or source.get("url") or source.get("source_id")
    return key if isinstance(key, str) else ""


def _next_source_number(source_ids: set[str]) -> int:
    numbers = [
        int(source_id[1:])
        for source_id in source_ids
        if source_id.startswith("S") and source_id[1:].isdigit()
    ]
    return max(numbers, default=0) + 1


def _next_unique_source_id(used_source_ids: set[str], start: int) -> str:
    candidate_number = start
    while True:
        candidate = f"S{candidate_number}"
        if candidate not in used_source_ids:
            used_source_ids.add(candidate)
            return candidate
        candidate_number += 1


def _remap_finding_source_ids(findings: object, remapped_ids: dict[str, str]) -> None:
    if not isinstance(findings, list):
        return
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        source_ids = finding.get("source_ids")
        if not isinstance(source_ids, list):
            continue
        finding["source_ids"] = [
            remapped_ids.get(source_id, source_id) if isinstance(source_id, str) else source_id
            for source_id in source_ids
        ]


def _add_counts(target: dict[str, int], counts: object) -> None:
    if not isinstance(counts, dict):
        return
    for key, value in counts.items():
        if isinstance(key, str) and isinstance(value, int):
            target[key] = target.get(key, 0) + value


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
