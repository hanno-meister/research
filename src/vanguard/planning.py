"""Structured research planning node."""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from .contracts import MAX_RESEARCH_TASKS, ResearchPlan, ResearchTask
from .langgraph_configuration import LangGraphConfig
from .prompts import RESEARCH_PLAN_PROMPT
from .state import AgentState
from .utils.collections import clean_strings, unique_preserving_order
from .utils.urls import (
    allowed_url_target_contains_target,
    allowed_url_target_text,
    normalize_allowed_url_target,
)


logger = logging.getLogger(__name__)


async def plan_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    """Convert the research brief into bounded future worker tasks."""

    research_brief = state.get("research_brief")
    if not research_brief:
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    logger.info("Planning research tasks", extra={"research_brief_characters": len(research_brief)})
    model = ChatOpenAI(
        model=runtime.context.large_model,
        base_url=runtime.context.openai_base_url,
        api_key=runtime.context.azure_openai_api_key,
        use_responses_api=False,
    )
    structured_model = model.with_structured_output(ResearchPlan)
    response = await structured_model.ainvoke(
        [
            HumanMessage(
                content=RESEARCH_PLAN_PROMPT.format(
                    research_intent=state["research_intent"],
                    selected_lance=_selected_lance_text(state),
                    research_brief=research_brief,
                    runtime_constraints=_runtime_constraints_text(state),
                    max_research_tasks=MAX_RESEARCH_TASKS,
                )
            )
        ]
    )

    if not isinstance(response, ResearchPlan):
        raise TypeError(f"Expected ResearchPlan, got {type(response).__name__}")

    tasks = _sanitized_tasks(response.tasks, state, research_brief)
    feasibility_notes = feasibility_notes_for_state(state, research_brief)
    logger.info("Planned research tasks", extra={"research_task_count": len(tasks)})
    update: dict[str, object] = {"research_tasks": [task.model_dump() for task in tasks]}
    if feasibility_notes:
        update["research_feasibility_notes"] = feasibility_notes
    return update


def _runtime_constraints_text(state: AgentState) -> str:
    allowed_domains = state.get("allowed_domains") or []
    return "\n".join(
        [
            f"allowed_domains: {list(allowed_domains) if allowed_domains else 'none'}",
            f"start_date: {state.get('start_date') or 'none'}",
            f"end_date: {state.get('end_date') or 'none'}",
        ]
    )


def _selected_lance_text(state: AgentState) -> str:
    lance = state.get("selected_lance") or {}
    if not isinstance(lance, dict):
        return "none"
    parts = [
        f"id: {str(lance.get('id', '')).strip()}",
        f"name: {str(lance.get('name', '')).strip()}",
        f"description: {str(lance.get('description', '')).strip()}",
    ]
    text = "\n".join(part for part in parts if not part.endswith(": "))
    return text or "none"


def _sanitized_tasks(
    tasks: list[ResearchTask],
    state: AgentState,
    research_brief: str,
    *,
    id_prefix: str = "task",
) -> list[ResearchTask]:
    allowed_domains = _allowed_targets_from_state(state)
    sanitized = [
        _sanitize_task(task, index, allowed_domains, id_prefix=id_prefix)
        for index, task in enumerate(tasks, start=1)
    ]
    sanitized = [task for task in sanitized if task.objective.strip()]
    if not sanitized:
        raise ValueError("Planning produced no usable research tasks")
    return sanitized


def feasibility_notes_for_state(state: AgentState, research_brief: str) -> list[str]:
    """Return broad source-policy feasibility notes for the current plan.

    This hook originally warned when a requested evidence category appeared
    infeasible under the current runtime constraints. Domain-specific heuristics
    were removed because they were too narrow for this general research workflow
    and produced false positives. Future checks should stay source-neutral, for
    example warning when allowed_domains are present and the brief asks for
    primary/official verification that may not be possible from the provided
    source universe.
    """
    return []


def _sanitize_task(
    task: ResearchTask, index: int, allowed_domains: tuple[str, ...], *, id_prefix: str = "task"
) -> ResearchTask:
    focused_domains = tuple(
        unique_preserving_order(
            allowed_url_target_text(normalize_allowed_url_target(domain))
            for domain in task.focused_domains
            if domain and domain.strip()
        )
    )
    if allowed_domains:
        focused_domains = tuple(
            _allowed_focus_target(domain, allowed_domains)
            for domain in focused_domains
            if _allowed_focus_target(domain, allowed_domains)
        )

    return task.model_copy(
        update={
            "id": f"{id_prefix}-{index}",
            "objective": task.objective.strip(),
            "rationale": task.rationale.strip(),
            "boundaries": clean_strings(task.boundaries),
            "key_questions": clean_strings(task.key_questions),
            "target_terms": clean_strings(task.target_terms),
            "focused_domains": list(focused_domains),
            "depends_on": _sanitize_depends_on(task.depends_on, index, id_prefix=id_prefix),
            "expected_output": task.expected_output.strip()
            or "Compact findings with source IDs and evidence paths.",
        }
    )


def _allowed_targets_from_state(state: AgentState) -> tuple[str, ...]:
    return tuple(
        unique_preserving_order(
            allowed_url_target_text(normalize_allowed_url_target(domain))
            for domain in state.get("allowed_domains", [])
            if isinstance(domain, str) and domain.strip()
        )
    )


def _allowed_focus_target(focused_domain: str, allowed_domains: tuple[str, ...]) -> str:
    focused_target = normalize_allowed_url_target(focused_domain)
    for allowed_domain in allowed_domains:
        allowed_target = normalize_allowed_url_target(allowed_domain)
        if allowed_url_target_contains_target(allowed_target, focused_target):
            return allowed_url_target_text(allowed_target)
    return ""


def _sanitize_depends_on(depends_on: list[str], index: int, *, id_prefix: str = "task") -> list[str]:
    dependencies = []
    for dependency in clean_strings(depends_on):
        mapped = _planned_task_id(dependency, id_prefix=id_prefix)
        if mapped and mapped != f"{id_prefix}-{index}":
            dependencies.append(mapped)
    return list(unique_preserving_order(dependencies))


def _planned_task_id(value: str, *, id_prefix: str = "task") -> str:
    stripped = value.strip()
    if stripped.startswith(f"{id_prefix}-") and stripped.removeprefix(f"{id_prefix}-").isdigit():
        return stripped
    if stripped.isdigit():
        return f"{id_prefix}-{stripped}"
    return stripped
