"""Structured models for research review."""

from pydantic import BaseModel, Field

from vanguard.planning import ResearchTask


class EvidenceReadRequest(BaseModel):
    """Evidence artifact the evaluator wants the orchestrator to inspect."""

    source_id: str = Field(
        description="A known source_id from research_sources whose raw evidence should be inspected."
    )
    reason: str = Field(description="Why this evidence matters for review.")


class ResearchEvaluation(BaseModel):
    """Structured evaluator output for research sufficiency."""

    sufficient: bool = Field(description="Whether research is ready for final reporting.")
    coverage_assessment: str = ""
    source_quality_assessment: str = ""
    contradiction_notes: list[str] = Field(default_factory=list)
    weak_or_unsupported_findings: list[str] = Field(default_factory=list)
    evidence_to_read: list[EvidenceReadRequest] = Field(default_factory=list)
    follow_up_tasks: list[ResearchTask] = Field(default_factory=list)
