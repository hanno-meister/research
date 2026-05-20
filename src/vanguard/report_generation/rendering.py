"""Deterministic final report rendering helpers."""

from __future__ import annotations

import re
from typing import Any

from .models import ReportDraft


PLACEHOLDER_COMPLETE_TITLE = "Trend Report: World Generation Models for Spatial Computing"
INTERNAL_SOURCE_ID_RE = re.compile(r"(?:\[S\d+\])+|\bS\d+\b(?!-)" )


def title_from_intent(intent: str) -> str:
    text = (intent or "").strip()
    if text.lower().startswith("find "):
        text = text[5:].strip()
    return text[:1].upper() + text[1:] if text else "Research"


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
    title = src.get("title") or src.get("source_id") or "Source"
    domain = src.get("canonical_domain") or ""
    url = source_url(src)
    if url:
        return f"[{title}]({url})" + (f" ({domain})" if domain else "")
    return f"{title}" + (f" ({domain})" if domain else "")


def append_source_urls(text: str, source_ids: list[str], report_sources: dict[str, dict[str, Any]]) -> str:
    urls = [u for u in (source_url(report_sources[sid]) for sid in source_ids if sid in report_sources) if u]
    urls = list(dict.fromkeys(urls))
    if not urls:
        return text
    label = "Source:" if len(urls) == 1 else "Sources:"
    return f"{text} {label} {', '.join(urls)}"


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


def render_complete_report(state, review: dict[str, Any], findings, report_sources, draft: ReportDraft) -> str:
    lines = [f"# {PLACEHOLDER_COMPLETE_TITLE}", "", "## Summary"]
    lines.append(
        append_source_urls(
            sanitize_report_text(draft.executive_summary.summary or (findings[0]["summary"] if findings else "Research synthesis completed from available evidence.")),
            list(dict.fromkeys(draft.executive_summary.source_ids)),
            report_sources,
        )
    )

    lines += ["", "## Why It Matters"]
    why_it_matters = draft.limitations.summary or "This matters for the research group and Lance context, and for company-wide IT consulting planning and delivery."
    lines.append(
        append_source_urls(
            sanitize_report_text(why_it_matters),
            list(dict.fromkeys(draft.limitations.source_ids)),
            report_sources,
        )
    )

    lines += ["", "## Trending Technologies"]
    key_takeaways = list(draft.key_findings.bullets)
    if not key_takeaways:
        key_takeaways = [f["summary"] for f in findings[:3] if f.get("summary")]
    if not key_takeaways:
        key_takeaways = ["No high-confidence findings were available."]
    for takeaway in key_takeaways[:3]:
        lines.append(
            f"- {append_source_urls(sanitize_report_text(takeaway), list(dict.fromkeys(draft.key_findings.source_ids)), report_sources)}"
        )

    lines += ["", "## Team Suggestions"]
    team_suggestions = draft.next_steps.bullets or [draft.next_steps.summary or "Continue validating the strongest claims and resolve remaining gaps."]
    for suggestion in team_suggestions[:3]:
        lines.append(
            f"- {append_source_urls(sanitize_report_text(suggestion), list(dict.fromkeys(draft.next_steps.source_ids)), report_sources)}"
        )

    lines += ["", "## Deep Dive"]
    deep_dive = draft.key_findings.summary or (findings[0]["summary"] if findings else "Focus on the most relevant technology from the available findings.")
    lines.append(sanitize_report_text(deep_dive))

    cited_source_ids: list[str] = []
    for finding in findings:
        for sid in finding.get("source_ids", []):
            if sid in report_sources and sid not in cited_source_ids:
                cited_source_ids.append(sid)
    source_index = {sid: idx + 1 for idx, sid in enumerate(cited_source_ids)}
    for finding in findings:
        urls = [u for u in (source_url(report_sources[sid]) for sid in finding.get("source_ids", []) if sid in report_sources) if u]
        citation_suffix = f" Sources: {', '.join(dict.fromkeys(urls))}" if urls else ""
        lines.append(f"- {sanitize_report_text(finding['summary'])}{citation_suffix}")
    lines += ["", "## Sources"]
    seen_urls: set[str] = set()
    for sid in cited_source_ids:
        src = report_sources[sid]
        if src.get("status") == "exclude":
            continue
        url = source_url(src)
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        lines.append(f"- {source_label(src)}")
    return "\n".join(lines)
