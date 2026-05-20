"""Data models for the research agent node."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from vanguard.research.search_gateway_models import SearchPolicy

from .recorder import ResearchRunRecorder


@dataclass
class ResearchSearchBudget:
    """Per-worker search budget shared by concurrent tool calls."""

    max_search_calls: int
    search_calls: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def reserve_search_call(self) -> bool:
        async with self._lock:
            if self.search_calls >= self.max_search_calls:
                return False
            self.search_calls += 1
            return True


@dataclass(frozen=True)
class ResearchAgentContext:
    """Runtime-only context hidden from the model-facing tool schema."""

    search_policy: SearchPolicy
    default_query: str
    default_highlight_query: str
    focused_domains: tuple[str, ...]
    task_id: str | None
    search_budget: ResearchSearchBudget
    results_per_provider: int
    filesystem_backend: Any
    recorder: ResearchRunRecorder


class ResearchAgentSource(BaseModel):
    source_id: str | None = None
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


class ResearchFinding(BaseModel):
    summary: str = Field(description="Compact task-scoped finding.")
    source_ids: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)


class ResearchAgentOutput(BaseModel):
    findings: list[ResearchFinding] = Field(
        description="Compact task-scoped findings with source IDs and evidence paths."
    )
    source_diversity_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Brief notes about source coverage, such as domain skew, duplicate-heavy "
            "results, weak primary-source coverage, or source constraints encountered "
            "while completing this task."
        ),
    )
