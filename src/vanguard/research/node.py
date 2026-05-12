"""LangGraph node implementation for research."""

import logging
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.state import AgentState
from vanguard.utils.urls import normalize_domain

from .agent import create_research_agent, filesystem_backend
from .models import ResearchAgentOutput, ResearchFinding, ResearchSearchBudget
from .policy import search_context_from_state
from .recorder import ResearchRunRecorder


logger = logging.getLogger(__name__)

MAX_SEARCH_CALLS_PER_WORKER = 2


async def conduct_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    research_brief = state.get("research_brief")
    if not research_brief:
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    backend = filesystem_backend()
    recorder = ResearchRunRecorder()
    agent = create_research_agent(runtime.context, backend=backend)
    tasks = _worker_tasks(state, research_brief)
    logger.info(
        "Starting bounded research workers",
        extra={
            "worker_count": len(tasks),
        },
    )

    worker_outputs = await asyncio.gather(
        *(
            _run_research_worker(
                agent=agent,
                state=state,
                research_brief=research_brief,
                task=task,
                backend=backend,
                recorder=recorder,
            )
            for task in tasks
        )
    )

    findings = []
    diversity_notes = []
    for task, output in zip(tasks, worker_outputs, strict=True):
        findings.extend(_structured_findings(output.findings, task, recorder))
        diversity_notes.extend(
            f"{task.id}: {note}" for note in output.source_diversity_notes
        )

    if recorder.search_attempts == 0:
        raise ValueError("Research workers completed without calling search_gateway")
    if findings and not recorder.sources():
        raise ValueError("Research workers produced findings without recorded sources")

    logger.info(
        "Research workers completed",
        extra={
            "worker_count": len(tasks),
            "finding_count": len(findings),
            "source_count": len(recorder.sources()),
            "evidence_artifact_count": len(recorder.evidence_artifacts()),
            "provider_counts": recorder.provider_counts(),
            "domain_counts": recorder.domain_counts(),
        },
    )
    return _state_update_from_parts(findings, diversity_notes, recorder)


@dataclass(frozen=True)
class ResearchWorkerTask:
    id: str
    objective: str
    boundaries: tuple[str, ...] = ()
    key_questions: tuple[str, ...] = ()
    preferred_source_types: tuple[str, ...] = ()
    focused_domains: tuple[str, ...] = ()
    expected_output: str = ""
    effort: str = "medium"


async def _run_research_worker(
    *,
    agent,
    state: AgentState,
    research_brief: str,
    task: ResearchWorkerTask,
    backend,
    recorder: ResearchRunRecorder,
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
        search_budget=ResearchSearchBudget(
            max_search_calls=MAX_SEARCH_CALLS_PER_WORKER
        ),
    )
    logger.info(
        "Starting research worker",
        extra={
            "task_id": task.id,
            "default_query": agent_context.default_query,
            "focused_domains": agent_context.focused_domains,
            "max_search_calls": agent_context.search_budget.max_search_calls,
            "allowed_domains": agent_context.search_policy.allowed_domains,
            "start_date": agent_context.search_policy.start_date.isoformat()
            if agent_context.search_policy.start_date
            else None,
            "end_date": agent_context.search_policy.end_date.isoformat()
            if agent_context.search_policy.end_date
            else None,
        },
    )
    search_attempts_before = recorder.search_attempts
    agent_result = await agent.ainvoke(
        _agent_input(research_brief, task),
        context=agent_context,
    )
    if recorder.search_attempts == search_attempts_before:
        raise ValueError(
            f"Research worker {task.id} completed without calling search_gateway"
        )

    output = agent_result.get("structured_response")
    if not isinstance(output, ResearchAgentOutput):
        raise TypeError(f"Expected ResearchAgentOutput, got {type(output).__name__}")
    return output


def _agent_input(
    research_brief: str, task: ResearchWorkerTask
) -> dict[str, list[HumanMessage]]:
    return {
        "messages": [
            HumanMessage(
                content=(
                    "Conduct bounded research for exactly one focused task. Use the "
                    "search_gateway tool, cite only source_id values and raw_content_path "
                    "values returned by the tool, and return only compact structured "
                    "findings and diversity notes. Stay within the task objective and "
                    "boundaries; do not research unrelated plan tasks. Do not return "
                    "source lists, evidence artifacts, provider counts, or domain counts; "
                    "those are tracked automatically. You have a hard budget of "
                    f"{MAX_SEARCH_CALLS_PER_WORKER} search_gateway calls for this task.\n\n"
                    f"Research brief:\n{research_brief}"
                    f"{_worker_task_text(task)}"
                )
            )
        ]
    }


def _worker_task_text(task: ResearchWorkerTask) -> str:
    return "\n\nFocused worker task:\n" + "\n".join(
        [
            f"- id: {task.id}",
            f"- objective: {task.objective}",
            f"- boundaries: {list(task.boundaries)}",
            f"- key_questions: {list(task.key_questions)}",
            f"- preferred_source_types: {list(task.preferred_source_types)}",
            f"- focused_domains: {list(task.focused_domains)}",
            f"- expected_output: {task.expected_output}",
            f"- effort: {task.effort}",
        ]
    )


def _worker_tasks(state: AgentState, research_brief: str) -> list[ResearchWorkerTask]:
    research_tasks = state.get("research_tasks") or []
    if not research_tasks:
        return [
            ResearchWorkerTask(
                id="task-1",
                objective=state.get("research_intent") or research_brief,
                expected_output="Compact findings with source IDs and evidence paths.",
            )
        ]

    allowed_domains = _allowed_domains_from_state(state)
    return [
        _worker_task_from_mapping(task, index, allowed_domains)
        for index, task in enumerate(research_tasks, start=1)
    ]


def _worker_task_from_mapping(
    task: Mapping[str, object], index: int, allowed_domains: set[str]
) -> ResearchWorkerTask:
    return ResearchWorkerTask(
        id=_string_field(task, "id") or f"task-{index}",
        objective=_string_field(task, "objective"),
        boundaries=tuple(_string_sequence(task.get("boundaries"))),
        key_questions=tuple(_string_sequence(task.get("key_questions"))),
        preferred_source_types=tuple(_string_sequence(task.get("preferred_source_types"))),
        focused_domains=tuple(
            _focused_domains(task.get("focused_domains"), allowed_domains)
        ),
        expected_output=_string_field(task, "expected_output"),
        effort=_string_field(task, "effort") or "medium",
    )


def _task_default_query(
    task: ResearchWorkerTask, state: AgentState, research_brief: str
) -> str:
    parts = [task.objective, *task.key_questions]
    query = " ".join(part for part in parts if part).strip()
    return query or state.get("research_intent") or research_brief


def _task_highlight_query(task: ResearchWorkerTask, research_brief: str) -> str:
    parts = [research_brief, task.objective, *task.key_questions]
    return "\n".join(part for part in parts if part)


def _structured_findings(
    findings: Sequence[ResearchFinding],
    task: ResearchWorkerTask,
    recorder: ResearchRunRecorder,
) -> list[dict[str, object]]:
    known_source_ids = recorder.known_source_ids()
    known_evidence_paths = recorder.known_evidence_paths()
    return [
        {
            "task_id": task.id,
            "summary": finding.summary,
            "source_ids": [
                source_id
                for source_id in finding.source_ids
                if source_id in known_source_ids
            ],
            "evidence_paths": [
                path
                for path in finding.evidence_paths
                if path in known_evidence_paths
            ],
        }
        for finding in findings
    ]


def _state_update_from_parts(
    findings: list[dict[str, object]],
    diversity_notes: list[str],
    recorder: ResearchRunRecorder,
):
    return {
        "research_findings": findings,
        "research_sources": recorder.sources(),
        "evidence_artifacts": recorder.evidence_artifacts(),
        "source_diversity_notes": diversity_notes,
        "search_provider_counts": recorder.provider_counts(),
        "search_domain_counts": recorder.domain_counts(),
    }


def _string_field(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _string_sequence(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _allowed_domains_from_state(state: AgentState) -> set[str]:
    return {normalize_domain(domain) for domain in state.get("allowed_domains", [])}


def _focused_domains(value: object, allowed_domains: set[str]) -> list[str]:
    if not allowed_domains:
        return []
    return [
        domain
        for domain in (normalize_domain(item) for item in _string_sequence(value))
        if domain in allowed_domains
    ]
