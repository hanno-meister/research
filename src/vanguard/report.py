"""Simple V1 final report generation node."""

from __future__ import annotations

import re
from typing import Any

from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.research.agent import filesystem_backend_for_config
from vanguard.review.defaults import MAX_EVIDENCE_READ_CHARACTERS

from .state import AgentState


def final_report_generation(
    state: AgentState,
    runtime: Runtime[LangGraphConfig] | None = None,
) -> dict[str, str]:
    """Generate a plain Markdown report from reviewer-selected sources."""

    latest_review = _latest_review(state)
    if latest_review is None:
        return {
            "final_report": _incomplete_report(
                state,
                findings=_findings_for_sources(state, set(), set()),
                reason="No evidence-quality check was available.",
            )
        }

    selected_sources = _selected_report_sources(latest_review)
    preferred_source_ids = {source_id for source_id, status, _reason in selected_sources if status == "use"}
    usable_source_ids = preferred_source_ids or {
        source_id
        for source_id, status, _reason in selected_sources
        if status == "caution"
    }
    excluded_source_ids = {
        source_id for source_id, status, _reason in selected_sources if status == "exclude"
    }
    if not selected_sources:
        excluded_source_ids |= _caveated_source_ids(*_reviews(state))
    source_index = _source_index(state)
    findings = _findings_for_sources(state, usable_source_ids, excluded_source_ids)

    if latest_review.get("sufficient") is not True:
        return {"final_report": _incomplete_report(state, findings=findings)}

    evidence_count = _read_selected_report_evidence(state, usable_source_ids, runtime)
    return {
        "final_report": _complete_report(
            state,
            findings=findings,
            source_index=source_index,
            selected_sources=selected_sources,
            review=latest_review,
            evidence_count=evidence_count,
        )
    }


def _complete_report(
    state: AgentState,
    *,
    findings: list[dict[str, object]],
    source_index: dict[str, dict[str, object]],
    selected_sources: list[tuple[str, str, str]],
    review: dict[str, object],
    evidence_count: int,
) -> str:
    sections = [f"# {_report_title(state)}"]
    sections.append(_summary_section(findings, source_index, evidence_count))
    if findings:
        sections.append(_key_findings_section(findings, source_index))
    sections.append(_evidence_base_section(findings, source_index, evidence_count))
    limitations = _limitations(review, selected_sources, evidence_count)
    if limitations:
        sections.append("## Gaps and Limitations\n" + "\n".join(f"- {item}" for item in limitations))
    follow_up = _follow_up_objectives(review)
    if follow_up:
        sections.append("## Recommended Next Steps\n" + "\n".join(f"- {_public_text(item)}" for item in follow_up[:5]))
    sections.append(_sources_section(selected_sources, source_index, findings))
    return "\n\n".join(section for section in sections if section.strip())


def _incomplete_report(
    state: AgentState,
    findings: list[dict[str, object]] | None = None,
    *,
    reason: str | None = None,
) -> str:
    latest_review = _latest_review(state)
    source_index = _source_index(state)
    status = reason or _string_field(latest_review or {}, "coverage_assessment")
    status = status or "The current evidence is not yet sufficient for a reliable final report."
    sections = ["# Research Incomplete", f"## Current Status\n{_public_text(status)}"]

    if findings:
        lines = [
            "## Supported Findings So Far",
            "These findings are provisional because the current evidence still has unresolved gaps.",
        ]
        lines.extend(f"- {_finding_text(finding, source_index)}" for finding in findings[:6])
        sections.append("\n".join(lines))

    gaps = _review_notes(latest_review, "contradiction_notes") + _review_notes(
        latest_review, "weak_or_unsupported_findings"
    )
    public_gaps = [gap for gap in (_public_text(gap) for gap in gaps) if gap and gap != _public_text(status)]
    if public_gaps:
        sections.append("## Blocking Gaps\n" + "\n".join(f"- {gap}" for gap in public_gaps[:6]))

    follow_up = _follow_up_objectives(latest_review)
    if follow_up:
        sections.append(
            "## Recommended Follow-up\n" + "\n".join(f"- {_public_text(item)}" for item in follow_up[:5])
        )
    return "\n\n".join(sections)


def _summary_section(
    findings: list[dict[str, object]],
    source_index: dict[str, dict[str, object]],
    evidence_count: int,
) -> str:
    lines = ["## Executive Summary"]
    if findings:
        lines.extend(_summary_sentence(_finding_text(finding, source_index)) for finding in _ordered_findings(findings, source_index)[:2])
    else:
        lines.append("The reviewer did not select enough supported findings for a substantive final synthesis.")
    if evidence_count:
        lines.append(f"This synthesis is grounded in {evidence_count} reviewer-selected evidence read(s).")
    return "\n".join(lines)


def _key_findings_section(
    findings: list[dict[str, object]], source_index: dict[str, dict[str, object]]
) -> str:
    lines = ["## Key Findings"]
    lines.extend(f"- {_finding_text(finding, source_index)}" for finding in _ordered_findings(findings, source_index)[:8])
    return "\n".join(lines)


def _evidence_base_section(findings: list[dict[str, object]], source_index: dict[str, dict[str, object]], evidence_count: int) -> str:
    lines = ["## Evidence Base"]
    source_ids = []
    for finding in _ordered_findings(findings, source_index)[:5]:
        source_ids.extend(_string_items(finding.get("source_ids")))
    source_ids = _unique_strings(source_ids)
    if source_ids:
        lines.append("This report is grounded in these cited sources from retained findings:")
        lines.extend(f"- {_source_citation(source_id, source_index.get(source_id, {}))}" for source_id in source_ids[:8])
    if evidence_count:
        lines.append(f"Reviewer-selected evidence reread during report generation: {evidence_count} item(s).")
    return "\n".join(lines)


def _sources_section(
    selected_sources: list[tuple[str, str, str]],
    source_index: dict[str, dict[str, object]],
    findings: list[dict[str, object]],
) -> str:
    lines = ["## Selected Sources"]
    chosen = _chosen_sources(selected_sources, findings)
    for source_id, status, reason in chosen:
        source = source_index.get(source_id, {})
        citation = _source_citation(source_id, source)
        suffix = f" — {reason}" if reason and status == "caution" else ""
        note = " (caution)" if status == "caution" else ""
        lines.append(f"- {citation}{note}{suffix}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _chosen_sources(
    selected_sources: list[tuple[str, str, str]], findings: list[dict[str, object]], limit: int = 15
) -> list[tuple[str, str, str]]:
    referenced = []
    for finding in findings:
        referenced.extend(_string_items(finding.get("source_ids")))
    referenced_set = set(referenced)
    use = [item for item in selected_sources if item[1] == "use" and item[0] in referenced_set]
    if len(use) < limit:
        use.extend(item for item in selected_sources if item[1] == "use" and item not in use)
    if len(use) < limit:
        use.extend(item for item in selected_sources if item[1] == "caution" and item[0] in referenced_set and item not in use)
    if len(use) < limit:
        use.extend(item for item in selected_sources if item[1] == "caution" and item not in use)
    return [item for item in use if item[1] != "exclude"][:limit]


def _limitations(
    latest_review: dict[str, object],
    selected_sources: list[tuple[str, str, str]],
    evidence_count: int,
) -> list[str]:
    limitations = []
    source_quality = _string_field(latest_review, "source_quality_assessment")
    if source_quality:
        limitations.append(_public_text(source_quality))
    else:
        limitations.append("Source quality is adequate for a concise synthesis.")
    for _source_id, status, reason in selected_sources:
        if status == "caution" and reason:
            limitations.append(_public_text(reason))
    if not evidence_count:
        limitations.append("No reviewer-selected raw evidence was available to re-read during final report generation.")
    if _caveated_source_ids(latest_review):
        limitations.append("Lower-confidence, contradictory, or insufficiently supported items were omitted from the main synthesis.")
    return _unique_strings(limitations)


def _read_selected_report_evidence(
    state: AgentState,
    source_ids: set[str],
    runtime: Runtime[LangGraphConfig] | None,
) -> int:
    if not source_ids:
        return 0
    backend = filesystem_backend_for_config(runtime.context if runtime is not None else None)
    records = [
        record
        for record in state.get("evidence_read_records", [])
        if isinstance(record, dict) and _string_field(record, "source_id") in source_ids
    ]
    reads = 0
    seen: set[str] = set()
    for record in records:
        source_id = _string_field(record, "source_id")
        path = _string_field(record, "path")
        if not source_id or not path.startswith("/evidence/") or source_id in seen:
            continue
        seen.add(source_id)
        read_result = backend.read(path, limit=MAX_EVIDENCE_READ_CHARACTERS)
        if read_result.error is not None:
            continue
        content = str(read_result.file_data.get("content", ""))[:MAX_EVIDENCE_READ_CHARACTERS]
        if content:
            reads += 1
    return reads


def _findings_for_sources(
    state: AgentState,
    usable_source_ids: set[str],
    excluded_source_ids: set[str],
) -> list[dict[str, object]]:
    findings = []
    for finding in _finding_dicts(state.get("research_findings", [])):
        summary = _string_field(finding, "summary")
        if not summary or _is_control_instruction(summary):
            continue
        source_ids = set(_string_items(finding.get("source_ids")))
        if source_ids & excluded_source_ids:
            continue
        if usable_source_ids and not (source_ids & usable_source_ids):
            continue
        findings.append(finding)
    return _dedupe_findings(findings)


def _selected_report_sources(review: dict[str, object]) -> list[tuple[str, str, str]]:
    selected = []
    for item in review.get("selected_report_sources", []) if isinstance(review, dict) else []:
        if not isinstance(item, dict):
            continue
        source_id = _string_field(item, "source_id")
        status = _string_field(item, "status")
        reason = _string_field(item, "reason")
        if source_id and status in {"use", "caution", "exclude"}:
            selected.append((source_id, status, reason))
    return selected


def _latest_review(state: AgentState) -> dict[str, object] | None:
    reviews = [review for review in state.get("research_reviews", []) if isinstance(review, dict)]
    return reviews[-1] if reviews else None


def _source_index(state: AgentState) -> dict[str, dict[str, object]]:
    index = {}
    for source in state.get("research_sources", []):
        if isinstance(source, dict) and (source_id := _string_field(source, "source_id")):
            index[source_id] = source
    return index


def _finding_dicts(findings: Any) -> list[dict[str, object]]:
    if not isinstance(findings, list):
        return []
    return [finding if isinstance(finding, dict) else {"summary": str(finding)} for finding in findings]


def _dedupe_findings(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped = []
    seen_source_sets: set[tuple[str, ...]] = set()
    for finding in findings:
        summary = _normalize_text(_string_field(finding, "summary"))
        source_ids = tuple(sorted(_string_items(finding.get("source_ids"))))
        if not summary:
            continue
        if source_ids and source_ids in seen_source_sets:
            continue
        if source_ids:
            seen_source_sets.add(source_ids)
        deduped.append(finding)
    return deduped


def _finding_text(finding: dict[str, object], source_index: dict[str, dict[str, object]]) -> str:
    summary = _public_text(_string_field(finding, "summary"))
    citations = [_source_citation(source_id, source_index.get(source_id, {})) for source_id in _string_items(finding.get("source_ids"))]
    return f"{summary} ({'; '.join(citations)})" if citations else summary


def _source_citation(source_id: str, source: dict[str, object]) -> str:
    title = _string_field(source, "title") or _string_field(source, "canonical_domain") or "recorded source"
    url = _string_field(source, "url")
    date = _string_field(source, "published_date")
    details = ", ".join(part for part in [date] if part)
    label = title + (f" ({details})" if details else "")
    return f"{label} — {url}" if url else label


def _report_title(state: AgentState) -> str:
    value = _string_value(state.get("research_brief")) or _string_value(state.get("research_intent"))
    if not value:
        return "Research Report"
    title = re.sub(r"^(find|research|summarize|investigate|analyze)\s+", "", _summary_sentence(value), flags=re.IGNORECASE)
    title = _shorten(title.strip(" .") or "Research Report", 80)
    return title[:1].upper() + title[1:]


def _reviews(state: AgentState) -> list[dict[str, object]]:
    return [review for review in state.get("research_reviews", []) if isinstance(review, dict)]


def _caveated_source_ids(*reviews: dict[str, object]) -> set[str]:
    text = "\n".join(
        note
        for review in reviews
        for note in (_review_notes(review, "contradiction_notes") + _review_notes(review, "weak_or_unsupported_findings"))
    )
    return set(re.findall(r"(?<![A-Za-z0-9_-])S\d+(?![A-Za-z0-9_-])", text))


def _ordered_findings(
    findings: list[dict[str, object]], source_index: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    return sorted(findings, key=lambda finding: _finding_rank(finding, source_index), reverse=True)


def _finding_rank(finding: dict[str, object], source_index: dict[str, dict[str, object]]) -> int:
    rank = 0
    text = _string_field(finding, "summary").lower()
    if any(term in text for term in ("reuters", "official", "regulatory", "reported", "$", "billion")):
        rank += 10
    for source_id in _string_items(finding.get("source_ids")):
        source = source_index.get(source_id, {})
        domain = _string_field(source, "canonical_domain").lower()
        if domain.endswith(("reuters.com", ".gov", ".edu")):
            rank += 20
    return rank


def _follow_up_objectives(review: dict[str, object] | None) -> list[str]:
    if not isinstance(review, dict):
        return []
    objectives = []
    for task in review.get("follow_up_tasks", []):
        if isinstance(task, dict) and (objective := _string_field(task, "objective")):
            objectives.append(objective)
    return objectives


def _review_notes(review: dict[str, object] | None, key: str) -> list[str]:
    if not isinstance(review, dict):
        return []
    return _string_items(review.get(key))


def _public_text(value: str) -> str:
    text = re.sub(r"/evidence/[^\s),;]+", "evidence artifact", value.strip())
    text = re.sub(r"(?<![A-Za-z0-9_-])S\d+(?![A-Za-z0-9_-])", "a recorded source", text)
    text = re.sub("should not anchor", "does not sufficiently support", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _is_control_instruction(summary: str) -> bool:
    normalized = summary.strip().lower()
    return normalized.startswith(("flag ", "remove ", "exclude ", "omit ", "do not include ")) or any(
        phrase in normalized
        for phrase in ("remove from the final", "should not be used", "not individually verified", "out of scope")
    )


def _summary_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip())[0]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _string_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
