"""Deterministic final report rendering helpers."""

from __future__ import annotations

import re
from typing import Any

from .models import CitedText, ReportDraft, TeamSuggestionDraft
from .source_policy import final_selected_sources


INTERNAL_SOURCE_ID_RE = re.compile(r"(?:\[S\d+\])+|\bS\d+\b(?!-)" )
URL_RE = re.compile(r"https?://\S+")
MAX_URLS_PER_CLAIM = 3


def title_from_intent(intent: str) -> str:
    text = (intent or "").strip()
    if text.lower().startswith("find "):
        text = text[5:].strip()
    return text[:1].upper() + text[1:] if text else "Research"


def trend_report_title(state: dict[str, Any]) -> str:
    lance = state.get("selected_lance") or {}
    if isinstance(lance, dict):
        lance_name = str(lance.get("name") or "").strip()
        if lance_name:
            return f"Trend Report: {lance_name}"
    return f"Trend Report: {title_from_intent(str(state.get('research_intent') or 'Research'))}"


def dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def sanitize_report_text(text: str) -> str:
    text = INTERNAL_SOURCE_ID_RE.sub("", text or "")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def source_url(src: dict[str, Any]) -> str | None:
    return src.get("url") or src.get("normalized_url")


def source_label(src: dict[str, Any]) -> str:
    title = source_title(src)
    domain = src.get("canonical_domain") or ""
    url = source_url(src)
    if url:
        return f"[{title}]({url})" + (f" ({domain})" if domain else "")
    return f"{title}" + (f" ({domain})" if domain else "")


def source_title(src: dict[str, Any]) -> str:
    title = sanitize_report_text(str(src.get("title") or src.get("source_id") or "Source"))
    return re.sub(r"\s+(?:[-–—|:]\s*)?(?:arXiv|NVIDIA Blog|MIT Technology Review)\s*$", "", title, flags=re.IGNORECASE).strip()


def selected_source_label(index: int, src: dict[str, Any]) -> str:
    title = source_title(src)
    linked_title = f"[{title}]({source_url(src)})" if source_url(src) else title
    return f"{index}. {linked_title}"


def subsection_title(text: str, fallback: str) -> str:
    clean = sanitize_report_text(text)
    if not clean:
        return fallback
    first_sentence = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0]
    if ":" in first_sentence:
        first_sentence = first_sentence.split(":", 1)[0]
    words = first_sentence.split()
    if len(words) > 8:
        first_sentence = " ".join(words[:8])
    return first_sentence.rstrip(".,;:") or fallback


def render_cited_subsections(
    lines: list[str],
    items: list[CitedText],
    report_sources: dict[str, dict[str, Any]],
    *,
    fallback_prefix: str,
    max_items: int,
) -> None:
    for index, item in enumerate(items[:max_items], start=1):
        text = sanitize_report_text(item.text)
        if not text:
            continue
        lines += ["", f"### {subsection_title(text, f'{fallback_prefix} {index}')}", ""]
        lines.append(append_source_urls(text, item.source_ids, report_sources))


def append_source_urls(text: str, source_ids: list[str], report_sources: dict[str, dict[str, Any]], *, max_urls: int = MAX_URLS_PER_CLAIM) -> str:
    links: list[str] = []
    seen_urls: set[str] = set()
    for source_id in preferred_source_ids(source_ids, report_sources):
        src = report_sources.get(source_id)
        if not src or not (url := source_url(src)) or url in seen_urls:
            continue
        title = source_title(src)
        links.append(f"[{title}]({url})")
        seen_urls.add(url)
    if max_urls > 0:
        links = links[:max_urls]
    if not links:
        return text
    label = "Source:" if len(links) == 1 else "Sources:"
    return f"{text} {label} {', '.join(links)}"


def preferred_source_ids(source_ids: list[str], report_sources: dict[str, dict[str, Any]]) -> list[str]:
    def key(source_id: str) -> tuple[int, int, int]:
        src = report_sources.get(source_id, {})
        status_rank = 0 if src.get("status") == "use" else 1
        source_type_rank = 1 if src.get("source_type") == "index_or_feed" else 0
        warnings = src.get("source_warnings") or []
        feed_rank = 1 if any("feed" in str(warning) or "index" in str(warning) for warning in warnings) else 0
        return (status_rank, source_type_rank, feed_rank)

    return sorted(list(dict.fromkeys(source_ids)), key=key)


def cited_texts_from_section(section, fallback: str = "") -> list[CitedText]:
    items = [item for item in section.paragraphs if sanitize_report_text(item.text)]
    if items:
        return items
    summary = sanitize_report_text(section.summary or fallback)
    return [CitedText(text=summary, source_ids=section.source_ids)] if summary else []


def cited_bullets_from_section(section, fallback_bullets: list[str] | None = None) -> list[CitedText]:
    items = [item for item in section.cited_bullets if sanitize_report_text(item.text)]
    if items:
        return items
    bullets = section.bullets or fallback_bullets or []
    return [CitedText(text=bullet, source_ids=section.source_ids) for bullet in bullets if sanitize_report_text(bullet)]


def render_cited_paragraphs(lines: list[str], items: list[CitedText], report_sources: dict[str, dict[str, Any]]) -> None:
    for item in items:
        lines.append(append_source_urls(sanitize_report_text(item.text), item.source_ids, report_sources))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()


def finding_paragraphs(findings, report_sources: dict[str, dict[str, Any]], *, max_paragraphs: int = 4, findings_per_paragraph: int = 3) -> list[str]:
    paragraphs: list[str] = []
    for start in range(0, min(len(findings), max_paragraphs * findings_per_paragraph), findings_per_paragraph):
        group = findings[start : start + findings_per_paragraph]
        texts = [sanitize_report_text(str(finding.get("summary", ""))) for finding in group]
        texts = [text for text in texts if text]
        if not texts:
            continue
        source_ids: list[str] = []
        for finding in group:
            for sid in finding.get("source_ids", []):
                if sid not in source_ids:
                    source_ids.append(sid)
        paragraphs.append(append_source_urls(" ".join(texts), source_ids, report_sources))
    return paragraphs


def clean_no_url(value: str) -> str:
    return sanitize_report_text(URL_RE.sub("", value or ""))


def render_team_suggestion(index: int, suggestion: TeamSuggestionDraft, report_sources: dict[str, dict[str, Any]]) -> list[str]:
    title = sanitize_report_text(suggestion.action) or f"Suggestion {index}"
    rows = [
        ("Action", append_source_urls(title, suggestion.source_ids, report_sources)),
        ("Owner role", clean_no_url(suggestion.owner_role) or "Technical Lead"),
        ("Pilot", clean_no_url(suggestion.pilot) or "Define a scoped PoC and document the evidence-backed decision criteria."),
        ("Target timing", clean_no_url(suggestion.target_timing) or "4-6 weeks"),
        ("Effort", suggestion.effort),
        ("Required skills", ", ".join(sanitize_report_text(skill) for skill in suggestion.required_skills if sanitize_report_text(skill)) or "Research, prototyping, evaluation"),
        ("Dependencies", clean_no_url(suggestion.dependencies) or "Access to candidate tools, sample data, and evaluation environment."),
        ("Risks & mitigations", clean_no_url(suggestion.risk_and_mitigations) or "Risk: weak evidence or tool immaturity. Mitigation: use a narrow pilot and explicit go/no-go metrics."),
        ("Success metric", clean_no_url(suggestion.success_metric) or "A reusable decision record with benchmark results and next-step recommendation."),
        ("Related technology", clean_no_url(suggestion.related_technology) or "Most relevant trending technology"),
    ]
    lines = [f"### {index}. {title}", "", "| Field | Recommendation |", "|---|---|"]
    lines.extend(f"| {field} | {value} |" for field, value in rows)
    return lines


def cited_source_ids_from_draft(draft: ReportDraft) -> list[str]:
    source_ids: list[str] = []

    def add(ids: list[str]) -> None:
        for sid in ids:
            if sid not in source_ids:
                source_ids.append(sid)

    for section in (
        draft.executive_summary,
        draft.key_findings,
        draft.limitations,
        draft.next_steps,
    ):
        add(section.source_ids)
        for item in [*section.paragraphs, *section.cited_bullets]:
            add(item.source_ids)
    for item in [*draft.why_it_matters.for_lance, *draft.why_it_matters.for_firm]:
        add(item.source_ids)
    for suggestion in draft.team_suggestions:
        add(suggestion.source_ids)
    return source_ids


def render_confidence_and_gaps(lines: list[str], state, review: dict[str, Any]) -> None:
    items: list[str] = []
    source_quality = sanitize_report_text(str(review.get("source_quality_assessment") or ""))
    if source_quality:
        items.append(source_quality)
    for gap in review.get("coverage_gaps", []) or []:
        if isinstance(gap, str) and sanitize_report_text(gap):
            items.append(sanitize_report_text(gap))
    for note in state.get("source_diversity_notes", []) or []:
        if isinstance(note, str) and sanitize_report_text(note):
            items.append(sanitize_report_text(note))
    items = dedupe_preserve(items)[:6]
    if not items:
        return
    lines += ["", "## Confidence and Gaps"]
    primary = " ".join(items[:3])
    lines += ["", primary]
    if len(items) > 3:
        lines += ["", " ".join(items[3:6])]


def render_incomplete_report(state, review: dict[str, Any] | None) -> str:
    from .findings import finding_summary

    lines = ["# Research Incomplete", "", f"# {title_from_intent(state.get('research_intent', 'Research'))}"]
    lines += ["", (review or {}).get("coverage_assessment") or "No evidence-quality check was available."]
    if review:
        unsupported_artifact_notes = [
            "A reviewed source does not sufficiently support claims from evidence artifact metadata."
            for note in review.get("contradiction_notes", []) or []
            if isinstance(note, str) and "/evidence/" in note
        ]
        lines.extend(dedupe_preserve(unsupported_artifact_notes))
    findings = [summary for f in state.get("research_findings", []) or [] if (summary := finding_summary(f)) is not None]
    if findings:
        lines += ["", "## Provisional Findings"] + [f"- {f}" for f in dedupe_preserve(findings[:8])]
    if review:
        follow_ups = [
            str(task.get("objective", "")).strip()
            for task in review.get("follow_up_tasks", []) or []
            if isinstance(task, dict) and str(task.get("objective", "")).strip()
        ]
        if follow_ups:
            lines += ["", "## Recommended Next Steps"] + [f"- {objective}" for objective in dedupe_preserve(follow_ups[:5])]
    return "\n".join(lines)


def render_complete_report(state, review: dict[str, Any], findings, report_sources, draft: ReportDraft, *, report_status: str = "sufficient") -> str:
    lines = [f"# {trend_report_title(state)}", "", "## Summary"]
    if report_status == "partial":
        partial_note = sanitize_report_text(
            str(
                review.get("coverage_assessment")
                or "The reviewer found enough supported evidence for a caveated synthesis, but important coverage gaps remain."
            )
        )
        lines += ["", f"> Partial report: {partial_note}", ""]
    render_cited_paragraphs(
        lines,
        cited_texts_from_section(
            draft.executive_summary,
            findings[0]["summary"] if findings else "Research synthesis completed from available evidence.",
        )[:3],
        report_sources,
    )

    lines += ["", "## Why It Matters"]
    lance_items = draft.why_it_matters.for_lance or cited_texts_from_section(
        draft.limitations,
        "For the selected Lance, the key question is which world-generation capabilities are ready to prototype and which still require downstream engineering.",
    )
    firm_items = draft.why_it_matters.for_firm or [
        CitedText(
            text="For the company, the trend matters because clients will need help separating demos from deployable spatial-computing workflows, integration architectures, governance, and measurable pilots.",
            source_ids=draft.limitations.source_ids,
        )
    ]
    lines += ["", "### For the Selected Lance"]
    render_cited_paragraphs(lines, lance_items[:3], report_sources)
    lines += ["", "### For the Company"]
    render_cited_paragraphs(lines, firm_items[:3], report_sources)

    lines += ["", "## Trending Technologies"]
    key_takeaways = cited_bullets_from_section(
        draft.key_findings,
        [f["summary"] for f in findings[:5] if f.get("summary")],
    )
    if not key_takeaways:
        key_takeaways = [CitedText(text="No high-confidence findings were available.")]
    render_cited_subsections(
        lines,
        key_takeaways,
        report_sources,
        fallback_prefix="Technology",
        max_items=5,
    )

    lines += ["", "## Team Suggestions"]
    if draft.team_suggestions:
        for index, suggestion in enumerate(draft.team_suggestions[:4], start=1):
            lines.extend(render_team_suggestion(index, suggestion, report_sources))
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
    else:
        team_suggestions = cited_bullets_from_section(
            draft.next_steps,
            [draft.next_steps.summary or "Continue validating the strongest claims and resolve remaining gaps."],
        )
        for suggestion in team_suggestions[:4]:
            lines.append(f"- {append_source_urls(sanitize_report_text(suggestion.text), suggestion.source_ids, report_sources)}")

    lines += ["", "## Deep Dive"]
    deep_dive_items = cited_texts_from_section(draft.key_findings)
    if deep_dive_items:
        render_cited_paragraphs(lines, deep_dive_items[:4], report_sources)
    else:
        paragraphs = finding_paragraphs(findings, report_sources)
        lines.extend(paragraphs or ["Focus on the most relevant technology from the available findings."])

    cited_source_ids: list[str] = cited_source_ids_from_draft(draft)
    for finding in findings:
        for sid in finding.get("source_ids", []):
            if sid in report_sources and sid not in cited_source_ids:
                cited_source_ids.append(sid)
    render_confidence_and_gaps(lines, state, review)
    lines += ["", "## Selected Sources"]
    for index, src in enumerate(final_selected_sources(report_sources, cited_source_ids), start=1):
        lines.append(f"- {selected_source_label(index, src)}")
    return "\n".join(lines)
