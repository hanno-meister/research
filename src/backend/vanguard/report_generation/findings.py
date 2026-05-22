"""Finding extraction helpers."""

from __future__ import annotations

from typing import Any

from vanguard.state import AgentState


def finding_summary(finding: dict[str, Any]) -> str | None:
    summary = finding.get("summary")
    if not isinstance(summary, str):
        return None
    summary = summary.strip()
    return summary or None


def finding_source_ids(finding: dict[str, Any]) -> list[str]:
    source_ids = finding.get("source_ids", [])
    if not isinstance(source_ids, list):
        return []
    return [source_id for source_id in source_ids if isinstance(source_id, str)]


def finding_id_for_index(index: int) -> str:
    return f"F{index + 1}"


def findings_with_ids(state: AgentState) -> list[dict[str, Any]]:
    findings = []
    for index, finding in enumerate(state.get("research_findings", []) or []):
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_id"):
            findings.append(finding)
        else:
            findings.append({**finding, "finding_id": finding_id_for_index(index)})
    return findings


def usable_findings_from_review(state: AgentState, review: dict[str, Any], report_sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    has_decisions = bool(review.get("selected_report_sources"))
    selected_finding_ids = {str(item.get("finding_id")) for item in review.get("selected_report_findings", []) or [] if isinstance(item, dict)}
    for finding in findings_with_ids(state):
        summary = finding_summary(finding)
        if summary is None:
            continue
        finding_id = str(finding.get("finding_id", ""))
        if selected_finding_ids and finding_id not in selected_finding_ids:
            continue
        source_ids = finding_source_ids(finding)
        sids = [sid for sid in source_ids if sid in report_sources]
        allowed_sids = [sid for sid in sids if (not has_decisions) or report_sources.get(sid, {}).get("status") in {"use", "caution"}]
        allowed_finding_status = {str(item.get("finding_id")): item.get("status") for item in review.get("selected_report_findings", []) or [] if isinstance(item, dict)}
        if allowed_sids and (not allowed_finding_status or allowed_finding_status.get(finding_id) in {"use", "caution"}):
            out.append({**finding, "summary": summary, "source_ids": allowed_sids})
    return out
