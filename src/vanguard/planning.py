"""Structured research planning node."""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from .langgraph_configuration import LangGraphConfig
from .prompts import RESEARCH_PLAN_PROMPT
from .state import AgentState
from .utils.collections import clean_strings, unique_preserving_order
from .utils.urls import normalize_domain


logger = logging.getLogger(__name__)


ResearchEffort = Literal["low", "medium", "high"]


class ResearchTask(BaseModel):
    """A bounded unit of work for a future research worker agent."""

    id: str = Field(description="Stable short task identifier, such as task-1.")
    objective: str = Field(description="Specific research objective for this worker task.")
    rationale: str = Field(description="Why this task is needed for the overall brief.")
    boundaries: list[str] = Field(
        default_factory=list,
        description="What this task should and should not cover to avoid overlap.",
    )
    key_questions: list[str] = Field(
        default_factory=list,
        description="Focused questions this task should answer.",
    )
    preferred_source_types: list[str] = Field(
        default_factory=list,
        description="Source types to prioritize, e.g. official docs, papers, primary sources.",
    )
    focused_domains: list[str] = Field(
        default_factory=list,
        description="Optional focus-domain hints. These do not override runtime policy.",
    )
    expected_output: str = Field(
        description="Compact description of the structured findings expected from the worker.",
    )
    effort: ResearchEffort = Field(description="Relative effort budget for this task.")


class ResearchPlan(BaseModel):
    """Structured output produced by the planning node."""

    tasks: list[ResearchTask] = Field(
        description="Bounded non-overlapping research tasks for worker agents."
    )


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
                    research_brief=research_brief,
                    runtime_constraints=_runtime_constraints_text(state),
                )
            )
        ]
    )

    if not isinstance(response, ResearchPlan):
        raise TypeError(f"Expected ResearchPlan, got {type(response).__name__}")

    tasks = _sanitized_tasks(response.tasks, state, research_brief)
    logger.info("Planned research tasks", extra={"research_task_count": len(tasks)})
    return {"research_tasks": [task.model_dump() for task in tasks]}


def _runtime_constraints_text(state: AgentState) -> str:
    allowed_domains = state.get("allowed_domains") or []
    return "\n".join(
        [
            f"allowed_domains: {list(allowed_domains) if allowed_domains else 'none'}",
            f"start_date: {state.get('start_date') or 'none'}",
            f"end_date: {state.get('end_date') or 'none'}",
        ]
    )


def _sanitized_tasks(
    tasks: list[ResearchTask], state: AgentState, research_brief: str
) -> list[ResearchTask]:
    allowed_domains = _normalized_allowed_domains(state)
    sanitized = [_sanitize_task(task, index, allowed_domains) for index, task in enumerate(tasks, start=1)]
    sanitized = [task for task in sanitized if task.objective.strip()]
    return sanitized or [_fallback_task(research_brief, allowed_domains)]


def _sanitize_task(
    task: ResearchTask, index: int, allowed_domains: tuple[str, ...]
) -> ResearchTask:
    focused_domains = tuple(
        unique_preserving_order(
            normalize_domain(domain)
            for domain in task.focused_domains
            if domain and domain.strip()
        )
    )
    if allowed_domains:
        focused_domains = tuple(domain for domain in focused_domains if domain in allowed_domains)

    return task.model_copy(
        update={
            "id": task.id.strip() or f"task-{index}",
            "objective": task.objective.strip(),
            "rationale": task.rationale.strip(),
            "boundaries": clean_strings(task.boundaries),
            "key_questions": clean_strings(task.key_questions),
            "preferred_source_types": clean_strings(task.preferred_source_types),
            "focused_domains": list(focused_domains),
            "expected_output": task.expected_output.strip()
            or "Compact findings with source IDs and evidence paths.",
        }
    )


def _normalized_allowed_domains(state: AgentState) -> tuple[str, ...]:
    return tuple(
        unique_preserving_order(
            normalize_domain(domain)
            for domain in state.get("allowed_domains", [])
            if domain and domain.strip()
        )
    )

def _fallback_task(research_brief: str, allowed_domains: tuple[str, ...]) -> ResearchTask:
    return ResearchTask(
        id="task-1",
        objective=research_brief.strip(),
        rationale="Fallback task preserving the full research brief because planning produced no usable tasks.",
        boundaries=["Cover the full research brief without inventing additional constraints."],
        key_questions=[],
        preferred_source_types=["authoritative and primary sources where available"],
        focused_domains=list(allowed_domains),
        expected_output="Compact structured findings with source IDs, evidence paths, confidence, and limitations.",
        effort="medium",
    )
