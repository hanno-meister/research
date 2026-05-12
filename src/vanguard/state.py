"""Graph state definitions and data structures for the vanguard agent."""

import operator
from datetime import date
from typing import Annotated

from langchain_core.messages import MessageLikeRepresentation
from pydantic import BaseModel, Field
from typing_extensions import TypedDict, NotRequired


###################
# Structured Outputs
###################
class ConductResearch(BaseModel):
    """Call this tool to conduct research on a specific topic."""
    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should be described in high detail (at least a paragraph).",
    )

class ResearchComplete(BaseModel):
    """Call this tool to indicate that the research is complete."""

class Summary(BaseModel):
    """Research summary with key findings."""

    summary: str
    key_excerpts: str

class ResearchQuestion(BaseModel):
    """Research question and brief for guiding research."""

    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )

###################
# State Definitions
###################

class AgentInputState(TypedDict):
    research_intent: str
    allowed_domains: NotRequired[list[str]]
    start_date: NotRequired[date | str]
    end_date: NotRequired[date | str]

class AgentState(TypedDict):
    research_intent: str
    allowed_domains: NotRequired[list[str]]
    start_date: NotRequired[date | str]
    end_date: NotRequired[date | str]
    research_brief: NotRequired[str]
    research_findings: NotRequired[Annotated[list[str], operator.add]]
    research_sources: NotRequired[Annotated[list[dict[str, str | None]], operator.add]]
    evidence_artifacts: NotRequired[Annotated[list[dict[str, str | int | None]], operator.add]]
    source_diversity_notes: NotRequired[Annotated[list[str], operator.add]]
    search_provider_counts: NotRequired[dict[str, int]]
    search_domain_counts: NotRequired[dict[str, int]]
    final_report: NotRequired[str]

class SupervisorState(TypedDict):
    """State for the supervisor that manages research tasks."""

    supervisor_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    research_intent: str
    research_brief: str
    research_findings: Annotated[list[str], operator.add]
    research_iterations: int

class ResearcherState(TypedDict):
    """State for individual researchers conducting research."""

    researcher_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    tool_call_iterations: int
    research_topic: str
    research_summary: str

class ResearcherOutputState(BaseModel):
    """Output state from individual researchers."""

    research_summary: str
