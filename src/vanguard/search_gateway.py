"""Policy-aware search gateway for external research providers.

V1 semantics intentionally trust provider-side filtering. The gateway validates
which constraints are sent to providers, normalizes returned results, and
deduplicates them, but it does not independently reject returned results for
domain/date policy compliance yet.
"""

from __future__ import annotations

import asyncio
import importlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from config import config


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


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
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        normalized_domains = tuple(
            normalize_domain(domain) for domain in self.allowed_domains if domain.strip()
        )
        object.__setattr__(self, "allowed_domains", tuple(dict.fromkeys(normalized_domains)))

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
        normalized_url = normalize_url(self.url)
        object.__setattr__(self, "normalized_url", normalized_url)
        object.__setattr__(self, "canonical_domain", canonical_domain_from_url(normalized_url))


@dataclass(frozen=True)
class DuplicateSearchResult:
    """A result removed during gateway deduplication."""

    result: NormalizedSearchResult
    duplicate_of_url: str


@dataclass(frozen=True)
class SearchGatewayResult:
    """Gateway response after provider calls, normalization, and dedupe."""

    results: list[NormalizedSearchResult]
    duplicates: list[DuplicateSearchResult]
    provider_counts: dict[str, int]
    domain_counts: dict[str, int]


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

        `focused_domains` is only allowed when `policy.allowed_domains` is set,
        and every focused domain must be a subset of that allowlist. This lets the graph
        target underrepresented domains without inventing new constraints.
        """

        policy = policy or SearchPolicy()
        normalized_focused_domains = self._validate_focused_domains(policy, focused_domains)

        provider_results = await asyncio.gather(
            *(
                provider.search(query, policy, normalized_focused_domains, highlight_query)
                for provider in self.providers
            )
        )
        flattened_results = [result for results in provider_results for result in results]
        results, duplicates = dedupe_results(flattened_results)

        return SearchGatewayResult(
            results=results,
            duplicates=duplicates,
            provider_counts=dict(Counter(result.provider for result in results)),
            domain_counts=count_domains(results),
        )

    @staticmethod
    def _validate_focused_domains(
        policy: SearchPolicy,
        focused_domains: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if not focused_domains:
            return ()

        normalized_focused_domains = tuple(
            dict.fromkeys(normalize_domain(domain) for domain in focused_domains if domain.strip())
        )
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


def normalize_domain(domain: str) -> str:
    """Normalize user/provider domains for allowlist and reporting."""

    value = domain.strip().lower()
    if not value:
        return value
    if "://" in value:
        value = urlsplit(value).netloc
    value = value.split("/", 1)[0]
    value = value.split(":", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    return value.rstrip(".")


def canonical_domain_from_url(url: str) -> str:
    """Extract a normalized domain from a URL."""

    return normalize_domain(urlsplit(url).netloc)


def normalize_url(url: str) -> str:
    """Normalize URLs for deduplication without changing the destination."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = normalize_domain(parts.netloc)
    path = parts.path.rstrip("/") or "/"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS
        and not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _required_api_key(name: str, value: SecretStr | None) -> str:
    if value is None:
        raise RuntimeError(f"Set {name} in .env or the environment to use this provider")
    return value.get_secret_value()
