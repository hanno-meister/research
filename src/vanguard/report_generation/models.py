"""Structured models for report generation."""

from typing import Literal

from pydantic import BaseModel, Field


class ReportSectionDraft(BaseModel):
    title: str = Field(default="")
    bullets: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    source_ids: list[str] = Field(default_factory=list)


class ReportDraft(BaseModel):
    status: Literal["sufficient", "incomplete"] = "sufficient"
    executive_summary: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    key_findings: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    limitations: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
    next_steps: ReportSectionDraft = Field(default_factory=ReportSectionDraft)
