"""Bounded follow-up research execution for review."""

from __future__ import annotations

import asyncio
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
) -> tuple[dict[str, Any], int]:
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
        )
    )

    findings = []
    diversity_notes = []
    for task, output in zip(tasks, worker_outputs, strict=True):
        findings.extend(_structured_findings(output.findings, task, recorder))
        diversity_notes.extend(
            f"follow-up {task.id}: {note}" for note in output.source_diversity_notes
        )
    return _state_update_from_parts(
        findings,
        diversity_notes,
        recorder,
        new_only=True,
    ), len(tasks) * max_search_calls_per_worker


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
