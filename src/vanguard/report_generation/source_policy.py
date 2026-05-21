"""Source selection and validation helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from vanguard.state import AgentState


def latest_review(state: AgentState) -> dict[str, Any] | None:
    reviews = [review for review in state.get("research_reviews", []) or [] if isinstance(review, dict)]
    return reviews[-1] if reviews else None


def mentioned_source_ids(texts: list[str]) -> set[str]:
    ids: set[str] = set()
    for text in texts:
        ids.update(re.findall(r"\bS\d+\b", text or ""))
    return ids


def report_sources_by_id(state: AgentState, review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = {str(s.get("source_id")): s for s in state.get("research_sources", []) or [] if s.get("source_id")}
    report_sources: dict[str, dict[str, Any]] = {}
    decision_items = review.get("selected_report_sources", [])
    if not isinstance(decision_items, list):
        raise ValueError("review.selected_report_sources must be a list")
    for decision in decision_items:
        if not isinstance(decision, dict):
            raise ValueError("review.selected_report_sources items must be dicts")
        source_id = str(decision.get("source_id", "")).strip()
        status = decision.get("status")
        if source_id not in sources:
            continue
        if status == "exclude":
            continue
        if status not in {"use", "caution"}:
            raise ValueError(f"Unsupported selected_report_sources status: {status!r}")
        report_sources[source_id] = {**sources[source_id], **decision}
    if report_sources:
        return report_sources
    banned = mentioned_source_ids(list(review.get("contradiction_notes", []) or []) + list(review.get("weak_or_unsupported_findings", []) or []))
    if sources:
        for sid, src in sources.items():
            if sid not in banned:
                report_sources[sid] = src
    else:
        from .findings import finding_source_ids

        for finding in state.get("research_findings", []) or []:
            for sid in finding_source_ids(finding):
                if sid not in banned:
                    report_sources[sid] = {"source_id": sid, "status": "use"}
    return report_sources


def final_selected_sources(
    report_sources: dict[str, dict[str, Any]],
    cited_source_ids: list[str],
    *,
    max_sources: int = 20,
    max_arxiv_sources: int = 8,
) -> list[dict[str, Any]]:
    """Return compact, user-facing selected sources from the reviewed source pool."""

    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    arxiv_count = 0
    cited_set = set(cited_source_ids)
    for source_id in _source_ids_for_final_selection(report_sources, cited_source_ids):
        if source_id not in cited_set:
            continue
        source = report_sources.get(source_id)
        if not source or source.get("status") == "exclude":
            continue
        if source.get("status") == "caution" and len(selected) >= max_sources // 2:
            continue
        if _is_low_value_source(source):
            continue
        url = _source_url(source)
        normalized_url = _dedupe_url(url)
        if normalized_url and normalized_url in seen_urls:
            continue
        domain = str(source.get("canonical_domain") or "")
        if domain == "arxiv.org" and arxiv_count >= max_arxiv_sources:
            continue
        if normalized_url:
            seen_urls.add(normalized_url)
        if domain == "arxiv.org":
            arxiv_count += 1
        selected.append(source)
        if len(selected) >= max_sources:
            break
    return selected


def _source_ids_for_final_selection(
    report_sources: dict[str, dict[str, Any]], cited_source_ids: list[str]
) -> list[str]:
    cited = [sid for sid in cited_source_ids if sid in report_sources]
    uncited = [sid for sid in report_sources if sid not in cited]
    return sorted(cited, key=lambda sid: _source_rank(report_sources[sid])) + sorted(
        uncited, key=lambda sid: _source_rank(report_sources[sid])
    )


def _source_rank(source: dict[str, Any]) -> tuple[int, int, int, str]:
    status_rank = 0 if source.get("status") == "use" else 1
    low_value_rank = 1 if _is_low_value_source(source) else 0
    domain = str(source.get("canonical_domain") or "")
    domain_rank = 0 if domain != "arxiv.org" else 1
    return (status_rank, low_value_rank, domain_rank, str(source.get("source_id") or ""))


def _is_low_value_source(source: dict[str, Any]) -> bool:
    if source.get("source_type") == "index_or_feed":
        return True
    warnings = " ".join(str(warning).lower() for warning in source.get("source_warnings") or [])
    if "generic_index_page" in warnings:
        return True
    url = str(source.get("url") or source.get("normalized_url") or "")
    parsed = urlparse(url)
    if parsed.netloc.endswith("arxiv.org") and parsed.path.startswith(("/list/", "/search/")):
        return True
    return False


def _source_url(source: dict[str, Any]) -> str | None:
    return source.get("url") or source.get("normalized_url")


def _dedupe_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if parsed.netloc.endswith("arxiv.org"):
        path = re.sub(r"v\d+$", "", path)
    return parsed._replace(path=path, query="", fragment="").geturl()
