"""URL and domain normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .collections import unique_preserving_order


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_domain(domain: str) -> str:
    """Normalize user/provider domains for allowlists and reporting."""

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


def normalize_domains(domains: Iterable[str]) -> tuple[str, ...]:
    """Normalize, drop empty values, and deduplicate domains in first-seen order."""

    return tuple(
        unique_preserving_order(
            normalize_domain(domain)
            for domain in domains
            if domain and domain.strip()
        )
    )


def canonical_domain_from_url(url: str) -> str:
    """Extract a normalized domain from a URL."""

    return normalize_domain(urlsplit(url).netloc)


def normalize_url_for_deduplication(url: str) -> str:
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


def normalize_search_query(query: str) -> str:
    """Normalize free-form provider search text without treating it as a URL."""

    return " ".join(query.split())


normalize_url = normalize_url_for_deduplication
