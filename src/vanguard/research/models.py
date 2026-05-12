"""Data models for the research agent node."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from vanguard.search_gateway import SearchPolicy

from .recorder import ResearchRunRecorder


@dataclass(frozen=True)
class ResearchAgentContext:
    """Runtime-only context hidden from the model-facing tool schema."""

    search_policy: SearchPolicy
    default_query: str
    default_highlight_query: str
    filesystem_backend: Any
    recorder: ResearchRunRecorder


class ResearchAgentSource(BaseModel):
    provider: str
    query: str
    url: str
    title: str | None = None
    summary: str | None = None
    raw_content_path: str | None = None
    published_date: str | None = None
    normalized_url: str
    canonical_domain: str


class ResearchAgentEvidenceArtifact(BaseModel):
    provider: str
    url: str
    title: str | None = None
    path: str
    content_sha256: str | None = None
    content_characters: int | None = None


class ResearchAgentOutput(BaseModel):
    findings: list[str] = Field(description="Compact research findings with source citations.")
    source_diversity_notes: list[str] = Field(default_factory=list)
