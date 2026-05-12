"""Final report generation node."""

import re
from collections.abc import Sequence

from .state import AgentState


def final_report_generation(state: AgentState):
    findings = _finding_dicts(state.get("research_findings", []))
    reviews = _reviews(state)
    latest_review = _latest_review(state)
    original_task_ids = _original_task_ids(state)
    caveated_findings = [
        finding for finding in findings if _is_caveated_finding(finding, reviews)
    ]
    follow_up_task_ids = _follow_up_task_ids(state, reviews, original_task_ids)
    follow_up_findings = [
        finding
        for finding in findings
        if finding not in caveated_findings
        and _is_follow_up_finding(finding, original_task_ids, follow_up_task_ids)
    ]
    regular_findings = [
        finding
        for finding in findings
        if finding not in follow_up_findings and finding not in caveated_findings
    ]

    sections = [
        "Final report",
        _executive_summary(latest_review),
        _findings_section("Key Findings", regular_findings),
    ]
    if follow_up_findings:
        sections.append(_findings_section("Corrected / Follow-up Findings", follow_up_findings))
    if caveated_findings:
        sections.append(_findings_section("Caveated Findings", caveated_findings))
    sections.append(_limitations_section(state, latest_review, reviews))

    return {"final_report": "\n\n".join(section for section in sections if section)}


def _finding_text(finding: object) -> str:
    if isinstance(finding, str):
        return finding
    if not isinstance(finding, dict):
        return str(finding)

    summary = str(finding.get("summary") or "")
    source_ids = finding.get("source_ids") or []
    evidence_paths = finding.get("evidence_paths") or []
    refs = []
    if source_ids:
        refs.append(f"sources: {', '.join(str(source_id) for source_id in source_ids)}")
    if evidence_paths:
        refs.append(f"evidence: {', '.join(str(path) for path in evidence_paths)}")
    if refs:
        return f"{summary} ({'; '.join(refs)})"
    return summary


def _finding_dicts(findings: Sequence[object]) -> list[dict[str, object]]:
    normalized = []
    for finding in findings:
        if isinstance(finding, dict):
            normalized.append(finding)
        else:
            normalized.append({"summary": str(finding)})
    return normalized


def _latest_review(state: AgentState) -> dict[str, object] | None:
    reviews = _reviews(state)
    return reviews[-1] if reviews else None


def _reviews(state: AgentState) -> list[dict[str, object]]:
    reviews = state.get("research_reviews") or []
    return [review for review in reviews if isinstance(review, dict)]


def _original_task_ids(state: AgentState) -> set[str]:
    return {
        task_id
        for task in state.get("research_tasks", [])
        if isinstance(task, dict) and isinstance(task_id := task.get("id"), str)
    }


def _follow_up_task_ids(
    state: AgentState,
    reviews: list[dict[str, object]],
    original_task_ids: set[str],
) -> set[str]:
    task_ids = _follow_up_task_ids_from_diversity_notes(state, original_task_ids)

    for review in reviews:
        follow_up_tasks = review.get("follow_up_tasks")
        if not isinstance(follow_up_tasks, list):
            continue
        for task in follow_up_tasks:
            if isinstance(task, dict) and isinstance(task_id := task.get("id"), str):
                stripped_task_id = task_id.strip()
                if stripped_task_id and stripped_task_id not in original_task_ids:
                    task_ids.add(stripped_task_id)
    return task_ids


def _follow_up_task_ids_from_diversity_notes(
    state: AgentState, original_task_ids: set[str]
) -> set[str]:
    task_ids = set()
    for note in _string_items(state.get("source_diversity_notes")):
        match = re.match(r"follow-up\s+([^:]+):", note)
        if match:
            task_id = match.group(1).strip()
            if task_id and task_id not in original_task_ids:
                task_ids.add(task_id)
    return task_ids


def _is_follow_up_finding(
    finding: dict[str, object],
    original_task_ids: set[str],
    follow_up_task_ids: set[str],
) -> bool:
    task_id = finding.get("task_id")
    if not isinstance(task_id, str):
        return False
    if follow_up_task_ids:
        return task_id in follow_up_task_ids
    return bool(original_task_ids) and task_id not in original_task_ids


def _is_caveated_finding(
    finding: dict[str, object], reviews: list[dict[str, object]]
) -> bool:
    if not reviews:
        return False
    review_text = _caveat_text(reviews).lower()
    if not review_text:
        return False

    for source_id in _string_items(finding.get("source_ids")):
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(source_id.lower())}(?![A-Za-z0-9_-])", review_text):
            return True
    for evidence_path in _string_items(finding.get("evidence_paths")):
        if evidence_path.lower() in review_text:
            return True
    return False


def _caveat_text(reviews: list[dict[str, object]]) -> str:
    caveats = []
    for review in reviews:
        caveats.extend(_string_items(review.get("contradiction_notes")))
        caveats.extend(_string_items(review.get("weak_or_unsupported_findings")))
    return "\n".join(caveats)


def _executive_summary(latest_review: dict[str, object] | None) -> str:
    if latest_review is None:
        return "## Executive Summary\nNo evaluator review was available; report is based on collected findings only."

    sufficient = latest_review.get("sufficient")
    status = "sufficient" if sufficient is True else "not fully sufficient"
    coverage = _string_field(latest_review, "coverage_assessment")
    if coverage:
        return f"## Executive Summary\nEvaluator status: {status}. {coverage}"
    return f"## Executive Summary\nEvaluator status: {status}."


def _findings_section(title: str, findings: list[dict[str, object]]) -> str:
    if not findings:
        return ""
    lines = [f"## {title}"]
    for finding in findings:
        lines.append(f"- {_finding_text(finding)}")
    return "\n".join(lines)


def _limitations_section(
    state: AgentState,
    latest_review: dict[str, object] | None,
    reviews: list[dict[str, object]],
) -> str:
    lines = ["## Limitations / Evidence Quality"]
    if latest_review is not None:
        for source_quality in _source_quality_assessments(reviews):
            lines.append(f"- {source_quality}")
    for review in reviews:
        for note in _string_items(review.get("contradiction_notes")):
            lines.append(f"- Contradiction/caveat: {note}")
        for note in _string_items(review.get("weak_or_unsupported_findings")):
            lines.append(f"- Weak or unsupported: {note}")

    for record in state.get("evidence_read_records", []):
        if not isinstance(record, dict):
            continue
        source_id = record.get("source_id")
        path = record.get("path")
        characters = record.get("content_characters")
        if isinstance(source_id, str) and isinstance(path, str):
            lines.append(
                f"- Raw evidence inspected for {source_id}: {path} ({characters} characters)."
            )

    diversity_notes = _string_items(state.get("source_diversity_notes"))
    if diversity_notes:
        lines.append("- Source diversity notes: " + " | ".join(diversity_notes))
    if len(lines) == 1:
        lines.append("- No evaluator caveats or evidence-quality notes were recorded.")
    return "\n".join(lines)


def _string_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _source_quality_assessments(reviews: list[dict[str, object]]) -> list[str]:
    assessments = []
    seen = set()
    for review in reviews:
        assessment = _string_field(review, "source_quality_assessment")
        if assessment and assessment not in seen:
            seen.add(assessment)
            assessments.append(assessment)
    return assessments
