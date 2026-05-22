"""Structured models for report generation."""

from typing import Literal

from pydantic import BaseModel, Field


class CitedText(BaseModel):
    text: str = Field(default="")
    source_ids: list[str] = Field(default_factory=list)


class ReportSectionDraft(BaseModel):
    title: str = Field(default="")
    bullets: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    source_ids: list[str] = Field(default_factory=list)
    paragraphs: list[CitedText] = Field(default_factory=list)
    cited_bullets: list[CitedText] = Field(default_factory=list)


class WhyItMattersDraft(BaseModel):
    for_lance: list[CitedText] = Field(default_factory=list)
    for_firm: list[CitedText] = Field(default_factory=list)


class TeamSuggestionDraft(BaseModel):
    action: str = Field(default="", description="Outcome-oriented one sentence describing what to do.")
    owner_role: str = Field(default="", description="Role, not a person, responsible for driving the suggestion.")
    pilot: str = Field(default="", description="Pilot or PoC scope. Do not include URLs.")
    target_timing: str = Field(default="", description="Relative timing such as '4-6 weeks' or 'next sprint'.")
    effort: Literal["S", "M", "L"] = "M"
    required_skills: list[str] = Field(default_factory=list, min_length=0, max_length=8)
    dependencies: str = Field(default="", description="Tools, data, approvals, or access needed. Do not include URLs.")
    risk_and_mitigations: str = Field(default="", description="Risks and mitigations. Do not include URLs.")
    success_metric: str = Field(default="", description="How success will be judged. Do not include URLs.")
    related_technology: str = Field(default="", description="Related trending technology or Deep Dive topic.")
    source_ids: list[str] = Field(default_factory=list)


class ReportDraft(BaseModel):
    status: Literal["sufficient", "partial", "incomplete"] = "sufficient"
    executive_summary: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    key_findings: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    limitations: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    next_steps: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    why_it_matters: WhyItMattersDraft = Field(default_factory=WhyItMattersDraft)
    team_suggestions: list[TeamSuggestionDraft] = Field(default_factory=list)
