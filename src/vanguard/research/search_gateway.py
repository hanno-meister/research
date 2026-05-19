"""Policy-aware search gateway for external research providers.

V1 semantics intentionally trust provider-side filtering. The gateway validates
which constraints are sent to providers, normalizes returned results, and
deduplicates them, but it does not independently reject returned results for
domain/date policy compliance yet.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections import Counter
from typing import Any, Iterable

from pydantic import SecretStr

from config import config
from vanguard.research.search_gateway_models import (
    DuplicateSearchResult,
    NormalizedSearchResult,
    ProviderSearchError,
    RejectedSearchResult,
    SearchGatewayError,
    SearchGatewayResult,
    SearchPolicy,
    SearchProvider,
)
from vanguard.utils.urls import normalize_domains


logger = logging.getLogger(__name__)


class SearchGateway:
    """Coordinates policy-aware searches across provider adapters."""

    def __init__(self, providers: Iterable[SearchProvider]) -> None:
        self.providers = tuple(providers)
        if not self.providers:
            raise SearchGatewayError("At least one search provider is required")

    async def search(
        self,
        query: str,
        policy: SearchPolicy | None = None,
        focused_domains: Iterable[str] | None = None,
        highlight_query: str | None = None,
    ) -> SearchGatewayResult:
        """Search all configured providers using user-provided constraints.

        `focused_domains` are optional per-call narrowing domains. When provided,
        every focused domain must be a subset of the policy allowlist and providers
        are asked to search only those domains. Accepted results are still filtered
        against the full policy allowlist as the authoritative boundary.
        """

        policy = policy or SearchPolicy()
        normalized_focused_domains = self._validate_focused_domains(policy, focused_domains)

        provider_results = await asyncio.gather(
            *(
                self._safe_provider_search(
                    provider,
                    query,
                    policy,
                    normalized_focused_domains,
                    highlight_query,
                )
                for provider in self.providers
            )
        )
        flattened_results = [result for results, _error in provider_results for result in results]
        provider_errors = [error for _results, error in provider_results if error is not None]
        accepted_results, rejected_results = enforce_domain_policy(flattened_results, policy=policy)
        results, duplicates = dedupe_results(accepted_results)

        return SearchGatewayResult(
            results=results,
            duplicates=duplicates,
            provider_counts=dict(Counter(result.provider for result in results)),
            domain_counts=count_domains(results),
            rejected_results=rejected_results,
            provider_errors=provider_errors,
        )

    @staticmethod
    async def _safe_provider_search(
        provider: SearchProvider,
        query: str,
        policy: SearchPolicy,
        focused_domains: tuple[str, ...],
        highlight_query: str | None,
    ) -> tuple[list[NormalizedSearchResult], ProviderSearchError | None]:
        try:
            results = await provider.search(query, policy, focused_domains, highlight_query)
            logger.info(
                "Search provider completed: provider=%s result_count=%s results=%s",
                provider.name,
                len(results),
                _search_result_log_records(results),
            )
            return results, None
        except Exception as exc:  # noqa: BLE001 - external provider failures must not abort graph runs
            provider_error = ProviderSearchError(
                provider=provider.name,
                error_type=type(exc).__name__,
                message=str(exc),
            )
            logger.warning(
                "Search provider failed: provider=%s error_type=%s error=%s",
                provider_error.provider,
                provider_error.error_type,
                provider_error.message,
                exc_info=True,
            )
            return [], provider_error

    @staticmethod
    def _validate_focused_domains(
        policy: SearchPolicy,
        focused_domains: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if not focused_domains:
            return ()

        normalized_focused_domains = normalize_domains(focused_domains)
        if not normalized_focused_domains:
            return ()

        if not policy.allowed_domains:
            raise SearchGatewayError(
                "focused_domains cannot be used when allowed_domains is unconstrained"
            )

        disallowed_focused_domains = sorted(
            set(normalized_focused_domains) - set(policy.allowed_domains)
        )
        if disallowed_focused_domains:
            raise SearchGatewayError(
                "focused_domains must be a subset of allowed_domains: "
                + ", ".join(disallowed_focused_domains)
            )

        return normalized_focused_domains


class ExaSearchAdapter:
    """Exa provider adapter using the optional `exa-py` package."""

    name = "exa"

    def __init__(
        self,
        client: Any | None = None,
        *,
        num_results: int = 5,
        highlights_max_characters: int = 1_000,
        text_max_characters: int | None = 20_000,
        include_summary: bool = True,
    ) -> None:
        self.client = client
        self.num_results = num_results
        self.highlights_max_characters = highlights_max_characters
        self.text_max_characters = text_max_characters
        self.include_summary = include_summary

    async def search(
        self,
        query: str,
        policy: SearchPolicy,
        focused_domains: tuple[str, ...] = (),
        highlight_query: str | None = None,
    ) -> list[NormalizedSearchResult]:
        client = self.client or self._default_client()
        include_domains = focused_domains or policy.allowed_domains
        kwargs: dict[str, Any] = {
            "type": "auto",
            "num_results": self.num_results,
            "contents": self._contents(highlight_query or query),
        }
        if include_domains:
            kwargs["include_domains"] = list(include_domains)
        if policy.start_date:
            kwargs["start_published_date"] = policy.start_date.isoformat()
        if policy.end_date:
            kwargs["end_published_date"] = policy.end_date.isoformat()

        response = await asyncio.to_thread(client.search, query, **kwargs)
        raw_results = _get_field(response, "results", []) or []
        return [self._normalize_result(query, result) for result in raw_results]

    def _contents(self, query: str) -> dict[str, Any]:
        contents: dict[str, Any] = {
            "highlights": {
                "max_characters": self.highlights_max_characters,
                "query": query,
            }
        }
        if self.text_max_characters is not None:
            contents["text"] = {"maxCharacters": self.text_max_characters}
        if self.include_summary:
            contents["summary"] = True
        return contents

    @staticmethod
    def _default_client() -> Any:
        try:
            exa_module = importlib.import_module("exa_py")
        except ImportError as exc:
            raise RuntimeError("Install exa-py to use ExaSearchAdapter") from exc

        api_key = _required_api_key("EXA_API_KEY", config.exa_api_key)
        return exa_module.Exa(api_key=api_key)

    def _normalize_result(self, query: str, result: Any) -> NormalizedSearchResult:
        highlights = _get_field(result, "highlights", None) or []
        summary = "\n".join(str(highlight) for highlight in highlights) or _get_field(
            result, "summary", None
        )
        return NormalizedSearchResult(
            provider=self.name,
            query=query,
            url=str(_get_field(result, "url", "")),
            title=_get_field(result, "title", None),
            summary=summary,
            raw_content=_get_field(result, "text", None),
            published_date=_get_field(result, "published_date", None)
            or _get_field(result, "publishedDate", None),
        )


class TavilySearchAdapter:
    """Tavily provider adapter using the optional `tavily-python` package."""

    name = "tavily"

    def __init__(
        self,
        client: Any | None = None,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_raw_content: bool | str = False,
    ) -> None:
        self.client = client
        self.max_results = max_results
        self.search_depth = search_depth
        self.include_raw_content = include_raw_content

    async def search(
        self,
        query: str,
        policy: SearchPolicy,
        focused_domains: tuple[str, ...] = (),
        highlight_query: str | None = None,
    ) -> list[NormalizedSearchResult]:
        client = self.client or self._default_client()
        include_domains = focused_domains or policy.allowed_domains
        kwargs: dict[str, Any] = {
            "max_results": self.max_results,
            "search_depth": self.search_depth,
        }
        if self.include_raw_content:
            kwargs["include_raw_content"] = self.include_raw_content
        if include_domains:
            kwargs["include_domains"] = list(include_domains)
        if policy.start_date:
            kwargs["start_date"] = policy.start_date.isoformat()
        if policy.end_date:
            kwargs["end_date"] = policy.end_date.isoformat()

        response = await asyncio.to_thread(client.search, query, **kwargs)
        raw_results = _get_field(response, "results", []) or []
        return [self._normalize_result(query, result) for result in raw_results]

    @staticmethod
    def _default_client() -> Any:
        try:
            tavily_module = importlib.import_module("tavily")
        except ImportError as exc:
            raise RuntimeError("Install tavily-python to use TavilySearchAdapter") from exc

        api_key = _required_api_key("TAVILY_API_KEY", config.tavily_api_key)
        return tavily_module.TavilyClient(api_key=api_key)

    def _normalize_result(self, query: str, result: Any) -> NormalizedSearchResult:
        return NormalizedSearchResult(
            provider=self.name,
            query=query,
            url=str(_get_field(result, "url", "")),
            title=_get_field(result, "title", None),
            summary=_get_field(result, "content", None),
            raw_content=_get_field(result, "raw_content", None),
            published_date=_get_field(result, "published_date", None),
        )


def count_domains(results: Iterable[NormalizedSearchResult]) -> dict[str, int]:
    """Count results by canonical domain."""

    return dict(Counter(result.canonical_domain for result in results if result.canonical_domain))


def _search_result_log_records(results: Iterable[NormalizedSearchResult]) -> list[dict[str, object]]:
    """Return compact result metadata suitable for logs.

    Avoid logging raw page content while still surfacing enough detail to debug
    provider behavior, filtering, and empty/low-quality result sets.
    """

    return [
        {
            "url": result.url,
            "normalized_url": result.normalized_url,
            "canonical_domain": result.canonical_domain,
            "title": result.title,
            "published_date": result.published_date,
            "summary_characters": len(result.summary or ""),
            "raw_content_characters": len(result.raw_content or ""),
        }
        for result in results
    ]


def underrepresented_domains(
    policy: SearchPolicy,
    results: Iterable[NormalizedSearchResult],
) -> list[str]:
    """Return allowed domains that are represented less than the current maximum.

    Empty `allowed_domains` means there is no finite allowlist to target.
    """

    if not policy.allowed_domains:
        return []

    counts = count_domains(results)
    if not counts:
        return list(policy.allowed_domains)
    max_count = max(counts.values())
    return [domain for domain in policy.allowed_domains if counts.get(domain, 0) < max_count]


def source_diversity_note(
    results: Iterable[NormalizedSearchResult],
    *,
    max_domain_share: float = 0.5,
) -> str | None:
    """Return a soft source-diversity note if one domain dominates results."""

    domain_counts = count_domains(results)
    total = sum(domain_counts.values())
    if total == 0:
        return None

    domain, count = max(domain_counts.items(), key=lambda item: item[1])
    share = count / total
    if share <= max_domain_share:
        return None
    return (
        f"Source diversity note: {count} of {total} accepted sources "
        f"({share:.0%}) came from {domain}. Additional searches against "
        "underrepresented allowed domains may be useful."
    )


def dedupe_results(
    results: Iterable[NormalizedSearchResult],
) -> tuple[list[NormalizedSearchResult], list[DuplicateSearchResult]]:
    """Deduplicate results by normalized URL."""

    seen: dict[str, NormalizedSearchResult] = {}
    unique_results: list[NormalizedSearchResult] = []
    duplicates: list[DuplicateSearchResult] = []
    for result in results:
        key = result.normalized_url
        if key in seen:
            duplicates.append(
                DuplicateSearchResult(result=result, duplicate_of_url=seen[key].normalized_url)
            )
            continue
        seen[key] = result
        unique_results.append(result)
    return unique_results, duplicates


def enforce_domain_policy(
    results: Iterable[NormalizedSearchResult],
    *,
    policy: SearchPolicy,
) -> tuple[list[NormalizedSearchResult], list[RejectedSearchResult]]:
    """Reject provider-returned results that violate domain constraints.

    Provider domain filters are an optimization; this function is the gateway's
    authoritative acceptance boundary for result domains.
    """

    allowed_domains = set(policy.allowed_domains)
    if not allowed_domains:
        return list(results), []

    accepted = []
    rejected = []
    for result in results:
        if result.canonical_domain in allowed_domains:
            accepted.append(result)
        else:
            rejected.append(RejectedSearchResult(result=result, reason="domain_not_allowed"))
    return accepted, rejected


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _required_api_key(name: str, value: SecretStr | None) -> str:
    if value is None:
        raise RuntimeError(f"Set {name} in .env or the environment to use this provider")
    return value.get_secret_value()
