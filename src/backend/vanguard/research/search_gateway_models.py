"""Data contracts for policy-aware search gateway providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from vanguard.utils.urls import (
    AllowedUrlTarget,
    canonical_domain_from_url,
    normalize_allowed_url_targets,
    normalize_domains,
    normalize_url_for_deduplication,
)


class SearchGatewayError(ValueError):
    """Raised when a search request violates gateway-level policy."""


@dataclass(frozen=True)
class SearchPolicy:
    """User-provided search constraints.

    Empty/None fields mean unconstrained for that dimension:
    - allowed_domains=() -> no domain constraint
    - start_date=None -> no lower publication-date bound
    - end_date=None -> no upper publication-date bound
    """

    allowed_domains: tuple[str, ...] = ()
    allowed_url_targets: tuple[AllowedUrlTarget, ...] = field(init=False, default=())
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        raw_allowed_domains = tuple(self.allowed_domains)
        object.__setattr__(self, "allowed_url_targets", normalize_allowed_url_targets(raw_allowed_domains))
        object.__setattr__(self, "allowed_domains", normalize_domains(raw_allowed_domains))

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise SearchGatewayError("start_date must be before or equal to end_date")

@dataclass(frozen=True)
class NormalizedSearchResult:
    """Compact common result shape returned by all provider adapters.

    `summary` is intentionally not raw page content. It is the best compact
    provider-supplied evidence text for the source, such as Exa highlights /
    summary or Tavily content.
    """

    provider: str
    query: str
    url: str
    title: str | None = None
    summary: str | None = None
    raw_content: str | None = None
    published_date: str | None = None
    normalized_url: str = field(init=False)
    canonical_domain: str = field(init=False)

    def __post_init__(self) -> None:
        normalized_url = normalize_url_for_deduplication(self.url)
        object.__setattr__(self, "normalized_url", normalized_url)
        object.__setattr__(self, "canonical_domain", canonical_domain_from_url(normalized_url))


@dataclass(frozen=True)
class DuplicateSearchResult:
    """A result removed during gateway deduplication."""

    result: NormalizedSearchResult
    duplicate_of_url: str


@dataclass(frozen=True)
class RejectedSearchResult:
    """A result rejected by gateway-side policy enforcement."""

    result: NormalizedSearchResult
    reason: str


@dataclass(frozen=True)
class ProviderSearchError:
    """A provider failure captured so one bad provider does not abort a run."""

    provider: str
    error_type: str
    message: str


@dataclass(frozen=True)
class SearchGatewayResult:
    """Gateway response after provider calls, normalization, and dedupe."""

    results: list[NormalizedSearchResult]
    duplicates: list[DuplicateSearchResult]
    provider_counts: dict[str, int]
    domain_counts: dict[str, int]
    rejected_results: list[RejectedSearchResult] = field(default_factory=list)
    provider_errors: list[ProviderSearchError] = field(default_factory=list)


class SearchProvider(Protocol):
    """Protocol implemented by concrete provider adapters."""

    name: str

    async def search(
        self,
        query: str,
        policy: SearchPolicy,
        focused_domains: tuple[str, ...] = (),
        highlight_query: str | None = None,
    ) -> list[NormalizedSearchResult]:
        """Run a provider search and return normalized results."""
        ...
