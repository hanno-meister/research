"""Source selection and validation helpers."""

from __future__ import annotations

import re
from typing import Any

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
