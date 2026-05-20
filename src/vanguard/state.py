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

###################
# State Definitions
###################

class AgentInputState(TypedDict):
    research_intent: str
    selected_lance: NotRequired[dict[str, str]]
    allowed_domains: NotRequired[list[str]]
    start_date: NotRequired[date | str]
    end_date: NotRequired[date | str]

class AgentState(TypedDict):
    """Shared LangGraph state for the research workflow.

    Fields:
        research_intent: User's original research request.
        selected_lance: Optional internal research Lance context for audience and relevance.
        allowed_domains: Optional hard allowlist for search result domains.
        start_date: Optional lower publication-date bound for searches.
        end_date: Optional upper publication-date bound for searches.
        research_brief: Normalized research question/brief generated from the intent.
        research_tasks: Planned worker tasks. Replaced as a whole, not appended.
        research_findings: Append-only compact findings from research workers.
            Each finding should include a summary plus recorder-owned source_ids and
            evidence_paths.
        research_sources: Append-only source metadata recorded from search results.
            Source IDs are Python-owned and used for citations and review decisions.
        evidence_artifacts: Append-only metadata for available virtual evidence files
            under ``/evidence/...``. This does not contain raw evidence content.
        research_feasibility_notes: Append-only notes about source-policy constraints
            or impossible coverage under the current runtime policy.
        source_diversity_notes: Append-only notes about domain/source skew, duplicates,
            weak source coverage, or follow-up source-diversity repairs.
        research_reviews: Append-only structured review records, including sufficiency,
            source-quality assessment, evidence-read requests, follow-up tasks, and
            reviewer-selected report sources.
        evidence_read_records: Append-only metadata for evidence files selected and
            read during review/final reporting. Does not contain raw snippet content.
        search_provider_counts: Latest aggregate accepted-source counts by provider.
        search_domain_counts: Latest aggregate accepted-source counts by domain.
        final_report: Rendered Markdown final or incomplete report.

    List-valued fields annotated with ``operator.add`` are append-only graph outputs;
    nodes should return lists for those fields so LangGraph can merge them correctly.
    """

    research_intent: str
    selected_lance: NotRequired[dict[str, str]]
    allowed_domains: NotRequired[list[str]]
    start_date: NotRequired[date | str]
    end_date: NotRequired[date | str]
    research_brief: NotRequired[str]
    research_tasks: NotRequired[list[dict[str, str | list[str]]]]
    research_findings: NotRequired[Annotated[list[dict[str, object]], operator.add]]
    research_sources: NotRequired[Annotated[list[dict[str, object]], operator.add]]
    evidence_artifacts: NotRequired[Annotated[list[dict[str, str | int | None]], operator.add]]
    research_feasibility_notes: NotRequired[Annotated[list[str], operator.add]]
    source_diversity_notes: NotRequired[Annotated[list[str], operator.add]]
    research_reviews: NotRequired[Annotated[list[dict[str, object]], operator.add]]
    evidence_read_records: NotRequired[Annotated[list[dict[str, str | int]], operator.add]]
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
