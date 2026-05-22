"""Deterministic report-bundle construction."""

from __future__ import annotations

from typing import Any, Literal

from vanguard.state import AgentState

from .findings import finding_summary, findings_with_ids
from .source_policy import latest_review, report_sources_by_id


ReportStatus = Literal["sufficient", "partial", "incomplete"]


def build_report_bundle(state: AgentState) -> dict[str, dict[str, object]]:
    """Build the only context final report writing is allowed to consume."""

    review = latest_review(state)
    if not review:
        return {"report_bundle": _empty_bundle(state, None)}

    sources_by_id = report_sources_by_id(state, review)
    banned = _excluded_selected_source_ids(review)
    source_status = {source_id: str(source.get("status") or "use") for source_id, source in sources_by_id.items()}
    sources = [_bundle_source(source_id, source) for source_id, source in sources_by_id.items()]
    required_topics = _strings(review.get("required_report_topics"))
    coverage_gaps = _strings(review.get("coverage_gaps"))
    methodology_caveats: list[dict[str, object]] = []
    methodology_caveats.extend(_repair_methodology_caveats(state))

    findings: list[dict[str, object]] = []
    for finding in _selected_findings(state, review):
        source_ids = _finding_source_ids(finding)
        banned_source_ids = [sid for sid in source_ids if sid in banned]
        kept_source_ids = [sid for sid in source_ids if sid not in banned]
        if source_ids and banned_source_ids and not kept_source_ids:
            banned_finding_id = str(finding.get("finding_id") or "")
            methodology_caveats.append(
                {
                    "type": "dropped_banned_finding",
                    "finding_id": banned_finding_id,
                    "source_ids": banned_source_ids,
                    "message": "A finding was dropped because the latest review marked one of its sources as contradictory or weak.",
                }
            )
            continue
        finding_for_bundle = {**finding, "source_ids": kept_source_ids} if banned_source_ids else finding
        bundled = _bundle_finding(finding_for_bundle, review, sources_by_id, source_status)
        if bundled is None:
            methodology_caveats.append(
                {
                    "type": "dropped_finding_without_kept_citations",
                    "finding_id": str(finding.get("finding_id") or ""),
                    "message": "A selected finding was dropped because none of its citations referred to kept report sources.",
                }
            )
            continue
        bundled_citations = bundled.get("citation_source_ids", [])
        bundled_citation_source_ids = [
            sid for sid in bundled_citations if isinstance(sid, str)
        ] if isinstance(bundled_citations, list) else []
        pruned_source_ids = [sid for sid in source_ids if sid not in bundled_citation_source_ids]
        if pruned_source_ids:
            methodology_caveats.append(
                {
                    "type": "pruned_finding_citations",
                    "finding_id": bundled["finding_id"],
                    "pruned_source_ids": pruned_source_ids,
                }
            )
        if _requires_missing_evidence_read(bundled, review, state):
            bundled["status"] = "caution"
            methodology_caveats.append(
                {
                    "type": "missing_evidence_read",
                    "finding_id": bundled["finding_id"],
                    "source_ids": bundled["citation_source_ids"],
                    "message": "Evidence reads were requested for this finding's sources but no matching evidence read record was available.",
                }
            )
        if _caution_only_support(bundled, source_status) and not _sole_required_topic_coverage(bundled, required_topics, findings):
            methodology_caveats.append(
                {
                    "type": "dropped_caution_only_finding",
                    "finding_id": bundled["finding_id"],
                    "message": "A caution finding was dropped because its only supporting sources were also caution-rated.",
                }
            )
            continue
        if _caution_only_support(bundled, source_status):
            coverage_gaps.append(
                f"{bundled['finding_id']} is the sole available coverage for a required topic and is supported only by caution-rated sources."
            )
        findings.append(bundled)

    status = _report_status(review, findings, sources_by_id)
    return {
        "report_bundle": {
            "status": status,
            "review_round": state.get("review_round", len(state.get("research_reviews", []) or [])),
            "findings": findings,
            "sources": sources,
            "required_topics": required_topics,
            "coverage_gaps": _dedupe_strings(coverage_gaps),
            "contradiction_notes": _strings(review.get("contradiction_notes")),
            "methodology_caveats": _dedupe_caveats(methodology_caveats),
            "coverage_assessment": review.get("coverage_assessment") or "",
            "source_quality_assessment": review.get("source_quality_assessment") or "",
            "follow_up_tasks": review.get("follow_up_tasks", []) if isinstance(review.get("follow_up_tasks"), list) else [],
        }
    }


def _empty_bundle(state: AgentState, review: dict[str, Any] | None) -> dict[str, object]:
    return {
        "status": "incomplete",
        "review_round": state.get("review_round", 0),
        "findings": [],
        "sources": [],
        "required_topics": [],
        "coverage_gaps": _strings((review or {}).get("coverage_gaps")),
        "contradiction_notes": _strings((review or {}).get("contradiction_notes")),
        "methodology_caveats": [],
        "coverage_assessment": (review or {}).get("coverage_assessment") or "No evidence-quality check was available.",
        "source_quality_assessment": (review or {}).get("source_quality_assessment") or "",
        "follow_up_tasks": [],
    }


def _bundle_source(source_id: str, source: dict[str, Any]) -> dict[str, object]:
    metadata = {key: value for key, value in source.items() if key not in {"status", "reason", "diversity_caveat"}}
    bundled: dict[str, object] = {
        "source_id": source_id,
        "metadata": metadata,
        "status": source.get("status") or "use",
    }
    if source.get("diversity_caveat"):
        bundled["diversity_caveat"] = source["diversity_caveat"]
    if source.get("reason"):
        bundled["reason"] = source["reason"]
    return bundled


def _selected_findings(state: AgentState, review: dict[str, Any]) -> list[dict[str, Any]]:
    findings = findings_with_ids(state)
    decisions = {str(item.get("finding_id")): item for item in review.get("selected_report_findings", []) or [] if isinstance(item, dict)}
    if not decisions:
        return [finding for finding in findings if finding_summary(finding)]
    selected = []
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        decision = decisions.get(finding_id)
        if not decision or decision.get("status") == "exclude":
            continue
        if decision.get("status") not in {"use", "caution"}:
            raise ValueError(f"Unsupported selected_report_findings status: {decision.get('status')!r}")
        selected.append({**finding, "status": decision.get("status"), "reason": decision.get("reason")})
    return selected


def _bundle_finding(
    finding: dict[str, Any],
    review: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    source_status: dict[str, str],
) -> dict[str, object] | None:
    summary = finding_summary(finding)
    if summary is None:
        return None
    citation_source_ids = [sid for sid in finding.get("source_ids", []) or [] if isinstance(sid, str) and sid in sources_by_id]
    if not citation_source_ids:
        return None
    finding_id = str(finding.get("finding_id") or "")
    status = str(finding.get("status") or _finding_decision_status(review, finding_id) or "use")
    if status not in {"use", "caution"}:
        return None
    return {
        "finding_id": finding_id,
        "content": summary,
        "summary": summary,
        "status": status,
        "provenance": _finding_provenance(finding),
        "citation_source_ids": citation_source_ids,
        "source_ids": citation_source_ids,
        "supporting_source_statuses": {sid: source_status.get(sid, "use") for sid in citation_source_ids},
    }


def _finding_source_ids(finding: dict[str, Any]) -> list[str]:
    return [sid for sid in finding.get("source_ids", []) or [] if isinstance(sid, str)]


def _excluded_selected_source_ids(review: dict[str, Any]) -> set[str]:
    return {
        str(item.get("source_id")).strip()
        for item in review.get("selected_report_sources", []) or []
        if isinstance(item, dict) and item.get("status") == "exclude" and str(item.get("source_id", "")).strip()
    }


def _finding_decision_status(review: dict[str, Any], finding_id: str) -> str | None:
    for item in review.get("selected_report_findings", []) or []:
        if isinstance(item, dict) and str(item.get("finding_id")) == finding_id:
            return str(item.get("status"))
    return None


def _finding_provenance(finding: dict[str, Any]) -> dict[str, object]:
    keys = ("task_id", "produced_by", "repair_task_id", "research_topic")
    return {key: finding[key] for key in keys if key in finding}


def _requires_missing_evidence_read(bundle_finding: dict[str, object], review: dict[str, Any], state: AgentState) -> bool:
    requested = {
        str(item.get("source_id"))
        for item in review.get("evidence_to_read", []) or []
        if isinstance(item, dict) and item.get("source_id")
    }
    if not requested:
        return False
    read = {
        str(item.get("source_id"))
        for item in state.get("evidence_read_records", []) or []
        if isinstance(item, dict) and item.get("source_id")
    }
    cited = set(bundle_finding.get("citation_source_ids", []) or [])
    return bool(cited & requested - read)


def _caution_only_support(bundle_finding: dict[str, object], source_status: dict[str, str]) -> bool:
    if bundle_finding.get("status") != "caution":
        return False
    cited = [sid for sid in bundle_finding.get("citation_source_ids", []) or [] if isinstance(sid, str)]
    return bool(cited) and all(source_status.get(sid) == "caution" for sid in cited)


def _sole_required_topic_coverage(bundle_finding: dict[str, object], required_topics: list[str], prior_findings: list[dict[str, object]]) -> bool:
    if not required_topics:
        return False
    content = str(bundle_finding.get("content") or "").lower()
    prior_text = " ".join(str(f.get("content") or "").lower() for f in prior_findings)
    for topic in required_topics:
        topic_text = topic.lower().strip()
        if topic_text and topic_text in content and topic_text not in prior_text:
            return True
    return False


def _repair_methodology_caveats(state: AgentState) -> list[dict[str, object]]:
    caveats = []
    for log in state.get("repair_logs", []) or []:
        if not isinstance(log, dict):
            continue
        for note in log.get("source_diversity_notes", []) or []:
            if isinstance(note, str) and note.strip():
                caveats.append(
                    {
                        "type": "repair_source_diversity",
                        "round": log.get("round"),
                        "message": note.strip(),
                    }
                )
    return caveats


def _report_status(
    review: dict[str, Any],
    findings: list[dict[str, object]],
    report_sources: dict[str, dict[str, Any]],
) -> ReportStatus:
    if review.get("core_brief_answerable") is False:
        return "incomplete"
    if not findings:
        return "incomplete"
    if review.get("sufficient") is True:
        return "sufficient"
    if not report_sources:
        return "incomplete"
    if review.get("selected_report_sources") or review.get("selected_report_findings") or review.get("required_report_topics"):
        return "partial"
    return "incomplete"


def _strings(value: object) -> list[str]:
    return [item.strip() for item in value or [] if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _dedupe_caveats(caveats: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    out = []
    for caveat in caveats:
        key = tuple(sorted((str(k), str(v)) for k, v in caveat.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(caveat)
    return out
