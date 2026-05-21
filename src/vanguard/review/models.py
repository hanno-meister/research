"""Structured models for research review."""

from typing import Literal

from pydantic import BaseModel, Field

from vanguard.contracts import ResearchTask


class EvidenceReadRequest(BaseModel):
    """Evidence artifact the evaluator wants the orchestrator to inspect."""

    source_id: str = Field(
        description="A known source_id from research_sources whose raw evidence should be inspected."
    )
    reason: str = Field(description="Why this evidence matters for review.")


class ReviewedSource(BaseModel):
    """Reviewer decision about a source's usefulness for final reporting."""

    source_id: str = Field(description="Known source_id from research_sources.")
    status: Literal["use", "caution", "exclude"] = Field(
        description=(
            "Whether this source should be used, used only with caution, or excluded "
            "from final report synthesis."
        )
    )
    reason: str = Field(description="Brief reason for this source decision.")


class ReviewedFinding(BaseModel):
    """Reviewer decision about a finding's usefulness for final reporting."""

    finding_id: str = Field(description="Python-owned finding identifier such as F1.")
    status: Literal["use", "caution", "exclude"] = Field(
        description="Whether this finding should be used, used cautiously, or excluded from final report synthesis."
    )
    reason: str = Field(description="Brief reason for this finding decision.")


class ResearchEvaluation(BaseModel):
    """Structured evaluator output for research sufficiency."""

    sufficient: bool = Field(
        description=(
            "True only if the findings answer the research brief with adequate "
            "coverage and source support; false if important gaps remain."
        )
    )
    core_brief_answerable: bool | None = Field(
        default=None,
        description=(
            "False only when the core brief cannot be answered at all from available evidence. "
            "Leave true or unset when a limited, caveated answer is supportable."
        ),
    )
    coverage_assessment: str = Field(
        default="",
        description="Brief assessment of whether findings cover the research brief and planned tasks.",
    )
    source_quality_assessment: str = Field(
        default="",
        description=(
            "Brief assessment of source strength, including primary-source coverage, "
            "domain diversity, and source limitations."
        ),
    )
    contradiction_notes: list[str] = Field(
        default_factory=list,
        description="Specific contradictions or unresolved conflicts between findings or sources.",
    )
    weak_or_unsupported_findings: list[str] = Field(
        default_factory=list,
        description=(
            "Findings that should be treated cautiously because cited evidence is weak, "
            "missing, indirect, stale, or insufficient."
        ),
    )
    required_report_topics: list[str] = Field(
        default_factory=list,
        description="Important source-supported topics, targets, or dimensions that the final report should cover.",
    )
    coverage_gaps: list[str] = Field(
        default_factory=list,
        description="Important target terms, topics, or dimensions that remain missing, weakly supported, or undercovered under the current runtime constraints.",
    )
    evidence_to_read: list[EvidenceReadRequest] = Field(
        default_factory=list,
        description=(
            "High-value sources to read by source_id for deeper context, validation, "
            "and final report synthesis without loading all raw evidence."
        ),
    )
    selected_report_sources: list[ReviewedSource] = Field(
        default_factory=list,
        description=(
            "Reviewer source decisions for final report synthesis after inspecting "
            "available metadata and any selected raw evidence."
        ),
    )
    selected_report_findings: list[ReviewedFinding] = Field(
        default_factory=list,
        description="Reviewer finding decisions for final report synthesis.",
    )
    follow_up_tasks: list[ResearchTask] = Field(
        default_factory=list,
        description=(
            "Targeted follow-up tasks needed to close remaining gaps; must stay within "
            "current allowed_domains."
        ),
    )
