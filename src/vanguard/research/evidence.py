"""Deterministic evidence file writing for search results."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from vanguard.search_gateway import NormalizedSearchResult


VIRTUAL_EVIDENCE_ROOT = "/evidence"

logger = logging.getLogger(__name__)


def write_evidence_file(
    result: NormalizedSearchResult,
    backend: Any,
) -> dict[str, str | int | None] | None:
    if not result.raw_content:
        return None

    content_hash = hashlib.sha256(result.raw_content.encode("utf-8")).hexdigest()
    document = _markdown_document(result)
    document_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
    path = _evidence_path(result, document_hash)
    write_result = backend.write(path, document)
    if write_result.error and "already exists" not in write_result.error:
        raise RuntimeError(write_result.error)
    logger.info(
        "Wrote evidence file" if not write_result.error else "Reused existing evidence file",
        extra={
            "provider": result.provider,
            "url": result.url,
            "path": path,
            "content_characters": len(result.raw_content),
        },
    )
    return {
        "provider": result.provider,
        "url": result.url,
        "title": result.title,
        "path": path,
        "content_sha256": content_hash,
        "content_characters": len(result.raw_content),
    }


def _evidence_path(result: NormalizedSearchResult, document_hash: str) -> str:
    domain = _slug(result.canonical_domain or "unknown-domain")
    title = _slug(result.title or result.normalized_url or "untitled")
    return f"{VIRTUAL_EVIDENCE_ROOT}/{result.provider}-{domain}-{title}-{document_hash[:12]}.md"


def _markdown_document(result: NormalizedSearchResult) -> str:
    return (
        f"# {result.title or result.url}\n\n"
        f"Provider: {result.provider}\n\n"
        f"URL: {result.url}\n\n"
        f"Canonical domain: {result.canonical_domain}\n\n"
        f"Published date: {result.published_date or 'unknown'}\n\n"
        "---\n\n"
        f"{result.raw_content}"
    )


def _slug(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug or "untitled")[:max_length].strip("-")
