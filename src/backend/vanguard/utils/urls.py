"""URL and domain normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AllowedUrlTarget:
    domain: str
    path_prefix: str = ""


def normalize_allowed_url_target(target: str) -> AllowedUrlTarget:
    value = target.strip()
    if not value:
        return AllowedUrlTarget(domain="")
    if "://" in value:
        parts = urlsplit(value)
        domain = normalize_domain(parts.netloc)
        path = parts.path or ""
    else:
        if "/" in value:
            domain_part, path_part = value.split("/", 1)
            domain = normalize_domain(domain_part)
            path = "/" + path_part
        else:
            domain = normalize_domain(value)
            path = ""
    if path and not path.startswith("/"):
        path = "/" + path
    if path and not path.endswith("/"):
        path = path + "/"
    return AllowedUrlTarget(domain=domain, path_prefix=path)


def normalize_allowed_url_targets(targets: Iterable[str]) -> tuple[AllowedUrlTarget, ...]:
    return tuple(
        unique_preserving_order(
            normalize_allowed_url_target(target)
            for target in targets
            if target and target.strip()
        )
    )


def allowed_url_target_matches_url(target: AllowedUrlTarget, url: str) -> bool:
    parts = urlsplit(url)
    domain = normalize_domain(parts.netloc)
    if domain != target.domain:
        return False
    if not target.path_prefix:
        return True
    path = parts.path or "/"
    prefix = target.path_prefix
    return path.startswith(prefix)


def allowed_url_target_text(target: AllowedUrlTarget) -> str:
    return f"{target.domain}{target.path_prefix}"


def allowed_url_target_contains_target(container: AllowedUrlTarget, candidate: AllowedUrlTarget) -> bool:
    if container.domain != candidate.domain:
        return False
    if not container.path_prefix:
        return True
    return candidate.path_prefix.startswith(container.path_prefix)


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
