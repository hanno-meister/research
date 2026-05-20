"""Shared structured-output contracts used across graph nodes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ResearchEffort = Literal["low", "medium", "high"]
MAX_RESEARCH_TASKS = 5


class ResearchQuestion(BaseModel):
    """Structured research brief generated from the user's research intent."""

    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )


class ResearchTask(BaseModel):
    """A bounded unit of work for a future research worker agent."""

    id: str = Field(
        default="",
        description="Optional task identifier. The application assigns the final stable task ID.",
    )
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
    target_terms: list[str] = Field(
        default_factory=list,
        description="Named systems, benchmarks, labs, datasets, methods, or capability terms this worker should explicitly check. These are search targets, not facts.",
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
        min_length=1,
        max_length=MAX_RESEARCH_TASKS,
        description="Bounded non-overlapping research tasks for worker agents.",
    )
