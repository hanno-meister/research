"""Final report generation node."""

import re
from collections.abc import Sequence

from pydantic import BaseModel, Field

from .state import AgentState
from .utils.urls import normalize_domain


class FinalReportCitation(BaseModel):
    source_id: str
    title: str | None = None
    url: str | None = None
    domain: str | None = None
    published_date: str | None = None
    source_quality: str | None = None
    source_type: str | None = None


class ApprovedReportFact(BaseModel):
    summary: str
    theme: str = "Other"
    importance: int = 0
    confidence: str = "medium"
    citations: list[FinalReportCitation] = Field(default_factory=list)


class FinalReportSection(BaseModel):
    heading: str
    bullets: list[str] = Field(default_factory=list)


class FinalReportOutput(BaseModel):
    title: str
    executive_summary: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)
    major_developments: list[FinalReportSection] = Field(default_factory=list)
    investor_implications: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class IncompleteReportOutput(BaseModel):
    title: str = "Research Incomplete"
    current_status: str
    supported_findings: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    recommended_follow_up: list[str] = Field(default_factory=list)
    evidence_reviewed: str | None = None


def final_report_generation(state: AgentState):
    findings = _finding_dicts(state.get("research_findings", []))
    reviews = _reviews(state)
    latest_review = _latest_review(state)
    source_index = _source_index(state)

    if latest_review is None:
        return {"final_report": _incomplete_report(state, findings, reviews, reason="No evidence-quality check was available.")}

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

    if latest_review.get("sufficient") is not True:
        provisional_findings = _dedupe_findings(regular_findings + follow_up_findings)
        return {"final_report": _incomplete_report(state, provisional_findings, reviews)}

    approved_findings = _dedupe_findings(regular_findings + follow_up_findings)
    report = _build_final_report(state, approved_findings, source_index, reviews)

    return {"final_report": _render_final_report(report)}


def _build_final_report(
    state: AgentState,
    findings: list[dict[str, object]],
    source_index: dict[str, dict[str, object]],
    reviews: list[dict[str, object]],
) -> FinalReportOutput:
    facts = _approved_report_facts(findings, source_index)
    return FinalReportOutput(
        title=_report_title_text(state),
        executive_summary=_executive_summary_paragraphs(state, facts),
        key_takeaways=[_fact_text(fact) for fact in facts[:5]],
        major_developments=_major_development_sections(facts),
        investor_implications=_investor_implication_bullets(facts),
        limitations=_limitation_bullets(state, reviews),
    )


def _render_final_report(report: FinalReportOutput) -> str:
    sections = [f"# {report.title}"]
    if report.executive_summary:
        sections.append("## Executive Summary\n" + "\n".join(report.executive_summary))
    if report.key_takeaways:
        sections.append("## Key Takeaways\n" + "\n".join(f"- {takeaway}" for takeaway in report.key_takeaways))
    if report.major_developments:
        lines = ["## Major Developments"]
        for section in report.major_developments:
            if not section.bullets:
                continue
            lines.append(f"### {section.heading}")
            lines.extend(f"- {bullet}" for bullet in section.bullets)
        if len(lines) > 1:
            sections.append("\n".join(lines))
    if report.investor_implications:
        sections.append(
            "## Implications\n"
            + "\n".join(f"- {implication}" for implication in report.investor_implications)
        )
    if report.limitations:
        sections.append("## Evidence and Limitations\n" + "\n".join(f"- {limitation}" for limitation in report.limitations))
    return "\n\n".join(sections)


def _render_incomplete_report(report: IncompleteReportOutput) -> str:
    sections = [f"# {report.title}", f"## Current Status\n{report.current_status}"]
    if report.supported_findings:
        sections.append(
            "## Supported Findings So Far\n"
            "These findings are provisional because the current evidence still has unresolved gaps.\n"
            + "\n".join(f"- {finding}" for finding in report.supported_findings)
        )
    if report.blocking_gaps:
        sections.append("## Blocking Gaps\n" + "\n".join(f"- {gap}" for gap in report.blocking_gaps))
    if report.recommended_follow_up:
        sections.append(
            "## Recommended Follow-up\n"
            + "\n".join(f"- {follow_up}" for follow_up in report.recommended_follow_up)
        )
    if report.evidence_reviewed:
        sections.append(f"## Evidence Reviewed\n- {report.evidence_reviewed}")
    return "\n\n".join(sections)


def _report_title_text(state: AgentState) -> str:
    brief = _string_value(state.get("research_brief")) or _string_value(state.get("research_intent"))
    if not brief:
        return "Research Brief"
    first_sentence = _summary_sentence_from_text(brief)
    title = re.sub(r"^(find|research|summarize|investigate|analyze)\s+", "", first_sentence, flags=re.IGNORECASE)
    title = _shorten(title.strip(" .") or "Research Brief", 72)
    if title.lower() == "research brief":
        return "Research Brief"
    return title[:1].upper() + title[1:]


def _is_control_or_review_instruction(summary: str) -> bool:
    normalized = summary.strip().lower()
    instruction_starts = (
        "flag ",
        "remove ",
        "exclude ",
        "omit ",
        "do not include ",
        "should be removed",
        "these should be removed",
        "out of scope",
    )
    if normalized.startswith(instruction_starts):
        return True
    instruction_phrases = (
        "remove from the final",
        "removed from the final",
        "final dated list",
        "not individually verified",
        "should not be used",
        "should not anchor",
    )
    return any(phrase in normalized for phrase in instruction_phrases)


def _theme_for_text(summary: str) -> str:
    text = summary.lower()
    if any(term in text for term in ["earnings", "revenue", "guidance", "stock", "investor", "market", "price", "$", "billion"]):
        return "Financial and Market Context"
    if any(term in text for term in ["regulatory", "legal", "lawsuit", "court", "policy", "export", "license", "government"]):
        return "Legal, Regulatory, and Policy Context"
    if any(term in text for term in ["partner", "partnership", "customer", "collaboration", "contract", "deal"]):
        return "Partnerships and Ecosystem"
    if any(term in text for term in ["launch", "product", "platform", "model", "service", "feature", "infrastructure", "technology"]):
        return "Products and Technical Developments"
    if any(term in text for term in ["risk", "competition", "competitor", "alternative", "pressure", "challenge"]):
        return "Risks and Competitive Context"
    return "Other"


def _importance_score(summary: str, citations: list[FinalReportCitation]) -> int:
    text = summary.lower()
    score = 0
    score += max((_source_quality_score(citation) for citation in citations), default=0)
    high_impact_terms = [
        "earnings",
        "revenue",
        "guidance",
        "investor",
        "billion",
        "regulatory",
        "legal",
        "partnership",
        "contract",
        "launch",
        "risk",
    ]
    score += sum(2 for term in high_impact_terms if term in text)
    if _is_control_or_review_instruction(summary):
        score -= 100
    return score


def _source_quality_score(citation: FinalReportCitation) -> int:
    quality = (citation.source_quality or "").lower()
    source_type = (citation.source_type or "").lower()
    if quality == "high" or source_type in {"primary", "official"}:
        return 24
    if quality == "medium":
        return 12
    if quality == "low":
        return 4
    domain = (citation.domain or "").lower()
    url = (citation.url or "").lower()
    combined = f"{domain} {url}"
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 30
    if any(primary in combined for primary in ["/investor", "official", "press", "newsroom"]):
        return 24
    if any(domain.endswith(established) for established in ["reuters.com", "apnews.com", "wsj.com", "ft.com", "bloomberg.com", "cnbc.com", "venturebeat.com", "technologyreview.com"]):
        return 18
    if any(domain.endswith(secondary) for secondary in ["deeplearning.ai", "datacenterknowledge.com", "tldr.tech"]):
        return 12
    if any(domain.endswith(weak) for weak in ["aol.com", "yahoo.com", "theneurondaily.com", "mexc.com", "bitget.com"]):
        return 4
    return 8


def _confidence_for_text(summary: str, citations: list[FinalReportCitation]) -> str:
    if "confidence: high" in summary.lower():
        return "high"
    if "confidence: low" in summary.lower():
        return "low"
    score = max((_source_quality_score(citation) for citation in citations), default=0)
    if score >= 24:
        return "high"
    if score <= 8:
        return "low"
    return "medium"


def _investor_implication_bullets(facts: list[ApprovedReportFact]) -> list[str]:
    if not facts:
        return []
    combined = "\n".join(fact.summary.lower() for fact in facts)
    bullets = []
    if any(term in combined for term in ["revenue", "growth", "earnings", "investor", "market", "demand"]):
        bullets.append("Financial or market implications should be treated as supported only where cited sources directly address them.")
    if any(term in combined for term in ["regulatory", "legal", "lawsuit", "court", "policy", "license", "export"]):
        bullets.append("Legal and regulatory implications require primary or established reporting before being stated as firm conclusions.")
    if any(term in combined for term in ["competition", "competitor", "alternative", "pressure", "risk"]):
        bullets.append("Competitive implications are clearest where the cited evidence distinguishes confirmed facts from inference or commentary.")
    if any(term in combined for term in ["partnership", "customer", "platform", "launch", "product", "service"]):
        bullets.append("Partnerships, product launches, and platform updates are strongest when supported by primary company or partner sources.")
    return bullets


def _approved_report_facts(
    findings: list[dict[str, object]],
    source_index: dict[str, dict[str, object]],
) -> list[ApprovedReportFact]:
    facts = []
    for finding in findings:
        summary = _string_field(finding, "summary")
        if not summary or _is_control_or_review_instruction(summary):
            continue
        citations = _citations_for_finding(finding, source_index)
        facts.append(
            ApprovedReportFact(
                summary=summary,
                theme=_theme_for_text(summary),
                importance=_importance_score(summary, citations),
                confidence=_confidence_for_text(summary, citations),
                citations=citations,
            )
        )
    return sorted(facts, key=lambda fact: fact.importance, reverse=True)


def _citations_for_finding(
    finding: dict[str, object], source_index: dict[str, dict[str, object]]
) -> list[FinalReportCitation]:
    citations = []
    for source_id in _string_items(finding.get("source_ids")):
        source = source_index.get(source_id, {})
        citations.append(
            FinalReportCitation(
                source_id=source_id,
                title=_string_field(source, "title") or None,
                url=_string_field(source, "url") or None,
                domain=_string_field(source, "canonical_domain") or None,
                published_date=_string_field(source, "published_date") or None,
                source_quality=_string_field(source, "source_quality") or None,
                source_type=_string_field(source, "source_type") or None,
            )
        )
    return citations


def _dedupe_findings(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    fingerprints: list[tuple[set[str], set[str], str]] = []
    for finding in findings:
        summary = _string_field(finding, "summary")
        if not summary:
            continue
        source_ids = set(_string_items(finding.get("source_ids")))
        evidence_paths = set(_string_items(finding.get("evidence_paths")))
        normalized = _normalize_finding_text(summary)
        if any(
            _is_duplicate_finding(source_ids, evidence_paths, normalized, existing)
            for existing in fingerprints
        ):
            continue
        deduped.append(finding)
        fingerprints.append((source_ids, evidence_paths, normalized))
    return deduped


def _is_duplicate_finding(
    source_ids: set[str],
    evidence_paths: set[str],
    normalized: str,
    existing: tuple[set[str], set[str], str],
) -> bool:
    existing_source_ids, existing_evidence_paths, existing_normalized = existing
    if normalized == existing_normalized:
        return True
    if source_ids and existing_source_ids and not source_ids.isdisjoint(existing_source_ids):
        return _text_similarity(normalized, existing_normalized) >= 0.34
    if evidence_paths and existing_evidence_paths and not evidence_paths.isdisjoint(existing_evidence_paths):
        return _text_similarity(normalized, existing_normalized) >= 0.34
    return False


def _normalize_finding_text(text: str) -> str:
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text.lower())
    text = re.sub(r"\b(sources?|source_ids?|evidence_paths?)\b", "", text)
    text = re.sub(r"[^a-z0-9$%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _text_similarity(left: str, right: str) -> float:
    left_terms = {term for term in left.split() if len(term) > 3}
    right_terms = {term for term in right.split() if len(term) > 3}
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def _fact_text(fact: ApprovedReportFact) -> str:
    citations = _render_citations(fact.citations)
    summary = _public_report_text(fact.summary, _citation_source_ids(fact.citations))
    if citations:
        return f"{summary} ({citations})"
    return summary


def _render_citations(citations: list[FinalReportCitation]) -> str:
    if not citations:
        return ""
    rendered = []
    for citation in citations[:4]:
        label = citation.title or citation.domain or "recorded source"
        label = _shorten(label, 80)
        details = ", ".join(
            part for part in [citation.domain, citation.published_date] if part
        )
        if details:
            label += f" ({details})"
        if citation.url:
            label += f" — {citation.url}"
        rendered.append(label)
    return "sources: " + "; ".join(rendered)


def _citation_source_ids(citations: list[FinalReportCitation]) -> set[str]:
    return {citation.source_id for citation in citations if citation.source_id}


def _major_development_sections(facts: list[ApprovedReportFact]) -> list[FinalReportSection]:
    sections = []
    for theme in [
        "Products and Technical Developments",
        "Partnerships and Ecosystem",
        "Financial and Market Context",
        "Legal, Regulatory, and Policy Context",
        "Risks and Competitive Context",
        "Other",
    ]:
        bullets = [_fact_text(fact) for fact in facts if fact.theme == theme]
        if bullets:
            sections.append(FinalReportSection(heading=theme, bullets=bullets))
    return sections


def _executive_summary_paragraphs(
    state: AgentState, facts: list[ApprovedReportFact]
) -> list[str]:
    if not facts:
        return ["The approved evidence did not produce a concise supported finding."]

    top_themes = _unique_strings([fact.theme for fact in facts if fact.theme != "Other"])
    paragraphs = []
    if top_themes:
        paragraphs.append(
            "Bottom line: the strongest supported themes are "
            + ", ".join(theme.lower() for theme in top_themes[:3])
            + "."
        )
    paragraphs.extend(
        _public_report_text(_summary_sentence_from_text(fact.summary), _citation_source_ids(fact.citations))
        for fact in facts[:2]
    )
    source_count = len([source for source in state.get("research_sources", []) if isinstance(source, dict)])
    if source_count:
        paragraphs.append(
            f"Confidence is based on {source_count} retained sources, with lower-confidence or contradictory items omitted from the synthesis."
        )
    return paragraphs


def _summary_sentence_from_text(text: str) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    return first_sentence


def _limitation_bullets(state: AgentState, reviews: list[dict[str, object]]) -> list[str]:
    bullets = []
    known_source_ids = set(_source_index(state))
    bullets.extend(_public_report_text(note, known_source_ids) for note in _string_items(state.get("research_feasibility_notes")))
    source_quality = _public_source_quality_summary(_source_quality_assessments(reviews))
    if source_quality:
        bullets.append(source_quality)
    if _excluded_reference_notes(reviews):
        bullets.append("Lower-confidence, contradictory, or insufficiently supported items were omitted from the main synthesis.")
    provider_counts = state.get("search_provider_counts")
    if isinstance(provider_counts, dict) and provider_counts:
        rendered_counts = ", ".join(f"{provider}: {count}" for provider, count in sorted(provider_counts.items()))
        bullets.append(f"Search coverage used multiple providers ({rendered_counts}).")
    return bullets or ["No material evidence-quality caveats were recorded."]


def _finding_text(finding: object, source_index: dict[str, dict[str, object]] | None = None) -> str:
    if isinstance(finding, str):
        return finding
    if not isinstance(finding, dict):
        return str(finding)

    summary = str(finding.get("summary") or "")
    source_ids = finding.get("source_ids") or []
    refs = _source_citations(source_ids, source_index or {})
    if refs:
        return f"{summary} ({'; '.join(refs)})"
    return summary


def _source_citations(source_ids: object, source_index: dict[str, dict[str, object]]) -> list[str]:
    refs = []
    if source_ids:
        formatted_sources = []
        for source_id in _string_items(source_ids):
            formatted_sources.append(_format_source_citation(source_id, source_index.get(source_id)))
        if formatted_sources:
            refs.append("sources: " + "; ".join(formatted_sources))
    return refs


def _format_source_citation(source_id: str, source: dict[str, object] | None) -> str:
    if not source:
        return "recorded source"
    title = _shorten(_string_field(source, "title"), 80)
    domain = _string_field(source, "canonical_domain")
    date = _string_field(source, "published_date")
    url = _string_field(source, "url")

    label = "recorded source"
    details = ", ".join(part for part in [domain, date] if part)
    if title:
        label = title
    if details:
        label += f" ({details})"
    if url:
        label += f" — {url}"
    return label


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


def _source_index(state: AgentState) -> dict[str, dict[str, object]]:
    index = {}
    for source in state.get("research_sources", []):
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if isinstance(source_id, str) and source_id.strip():
            index[source_id.strip()] = source
    return index


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


def _incomplete_report(
    state: AgentState,
    provisional_findings: list[dict[str, object]],
    reviews: list[dict[str, object]],
    *,
    reason: str | None = None,
) -> str:
    latest_review = reviews[-1] if reviews else None
    source_index = _source_index(state)
    known_source_ids = set(source_index)
    status = _current_status_text(latest_review, reason, known_source_ids=known_source_ids)
    report = IncompleteReportOutput(
        current_status=status,
        supported_findings=_provisional_finding_texts(provisional_findings, source_index),
        blocking_gaps=_blocking_gaps(reviews, status, known_source_ids=known_source_ids),
        recommended_follow_up=_recommended_follow_up(latest_review, state),
        evidence_reviewed=_evidence_reviewed_text(state),
    )
    return _render_incomplete_report(report)


def _current_status(latest_review: dict[str, object] | None, reason: str | None) -> str:
    lines = ["## Current Status"]
    if reason:
        lines.append(reason)
    elif latest_review is not None:
        coverage = _string_field(latest_review, "coverage_assessment")
        lines.append(coverage or "The current evidence is not yet sufficient for a reliable final report.")
    else:
        lines.append("Research has not been evaluated yet, so this should be treated as a draft.")
    return "\n".join(lines)


def _current_status_text(
    latest_review: dict[str, object] | None,
    reason: str | None,
    *,
    known_source_ids: set[str] | None = None,
) -> str:
    if reason:
        return _public_report_text(reason, known_source_ids)
    if latest_review is not None:
        coverage = _string_field(latest_review, "coverage_assessment")
        return _public_report_text(coverage, known_source_ids) or "The current evidence is not yet sufficient for a reliable final report."
    return "Research has not been evaluated yet, so this should be treated as a draft."


def _provisional_finding_texts(
    findings: list[dict[str, object]], source_index: dict[str, dict[str, object]]
) -> list[str]:
    texts = []
    for finding in findings:
        summary = _string_field(finding, "summary")
        if not summary or _is_control_or_review_instruction(summary):
            continue
        texts.append(_public_report_text(_finding_text(finding, source_index), set(source_index)))
    return texts[:5]


def _report_title(state: AgentState) -> str:
    return f"# {_report_title_text(state)}"


def _executive_summary(state: AgentState, findings: list[dict[str, object]]) -> str:
    lines = ["## Executive Summary"]
    if findings:
        lines.append(_summary_sentence(findings[0]))
        if len(findings) > 1:
            lines.append(_summary_sentence(findings[1]))
    else:
        lines.append("The approved evidence did not produce a concise supported finding.")

    source_count = len([source for source in state.get("research_sources", []) if isinstance(source, dict)])
    if source_count:
        lines.append(f"Confidence is based on {source_count} retained sources, with lower-confidence or contradictory items omitted from the synthesis.")
    else:
        lines.append("Confidence is limited because source metadata was not available in the final state.")
    return "\n".join(lines)


def _summary_sentence(finding: dict[str, object]) -> str:
    text = _string_field(finding, "summary")
    if not text:
        return "A supported finding was recorded without a detailed summary."
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    return _public_report_text(first_sentence)


def _key_takeaways(findings: list[dict[str, object]], source_index: dict[str, dict[str, object]]) -> str:
    if not findings:
        return ""
    lines = ["## Key Takeaways"]
    for finding in findings[:5]:
        lines.append(f"- {_public_report_text(_finding_text(finding, source_index))}")
    return "\n".join(lines)


def _findings_section(
    title: str,
    findings: list[dict[str, object]],
    *,
    provisional: bool = False,
    source_index: dict[str, dict[str, object]] | None = None,
) -> str:
    if not findings:
        return ""
    lines = [f"## {title}"]
    if provisional:
        lines.append("These findings are provisional because the current evidence still has unresolved gaps.")
    for finding in findings[5:] if title == "Major Developments" else findings:
        lines.append(f"- {_public_report_text(_finding_text(finding, source_index))}")
    return "\n".join(lines)


def _investor_implications(findings: list[dict[str, object]]) -> str:
    if not findings:
        return ""
    categories = []
    combined = "\n".join(_string_field(finding, "summary").lower() for finding in findings)
    if any(term in combined for term in ["demand", "revenue", "growth", "earnings", "market"]):
        categories.append("Market implications should be tied to direct financial or market-reaction evidence.")
    if any(term in combined for term in ["regulatory", "legal", "license", "export"]):
        categories.append("Legal and regulatory implications should be treated cautiously unless supported by primary or established reporting.")
    if any(term in combined for term in ["competition", "competitor", "alternative", "pressure"]):
        categories.append("Competitive implications should distinguish confirmed facts from analysis or inference.")
    if any(term in combined for term in ["software", "platform", "partnership", "customer", "launch"]):
        categories.append("Product, platform, and partnership updates are strongest when supported by primary company or partner sources.")
    if not categories:
        return ""
    return "## Implications\n" + "\n".join(f"- {category}" for category in categories)


def _blocking_gaps_section(reviews: list[dict[str, object]]) -> str:
    gaps = []
    latest_review = reviews[-1] if reviews else None
    if latest_review is not None:
        coverage = _string_field(latest_review, "coverage_assessment")
        if coverage:
            gaps.append(coverage)

    for review in reviews:
        gaps.extend(_string_items(review.get("contradiction_notes")))
        gaps.extend(_string_items(review.get("weak_or_unsupported_findings")))

    gaps = _unique_strings(gaps)
    if not gaps:
        return "## Blocking Gaps\n- No specific blocking gaps were recorded, but the current evidence is not sufficient for a final report."
    lines = ["## Blocking Gaps"]
    for gap in gaps[:8]:
        lines.append(f"- {gap}")
    return "\n".join(lines)


def _blocking_gaps(
    reviews: list[dict[str, object]],
    current_status: str,
    *,
    known_source_ids: set[str] | None = None,
) -> list[str]:
    gaps = []
    for review in reviews:
        gaps.extend(_string_items(review.get("contradiction_notes")))
        gaps.extend(_string_items(review.get("weak_or_unsupported_findings")))

    public_gaps = []
    for gap in _unique_strings(gaps):
        public_gap = _public_report_text(gap, known_source_ids)
        if public_gap and public_gap != current_status:
            public_gaps.append(public_gap)
    if public_gaps:
        return public_gaps[:6]
    return ["No specific blocking gaps were recorded, but the current evidence is not sufficient for a final report."]


def _recommended_follow_up_section(latest_review: dict[str, object] | None) -> str:
    if latest_review is None:
        return "## Recommended Follow-up\n- Run an evidence-quality check before treating this as a final report."
    follow_up_tasks = latest_review.get("follow_up_tasks")
    if not isinstance(follow_up_tasks, list) or not follow_up_tasks:
        return "## Recommended Follow-up\n- Resolve the blocking gaps above before producing a final report."

    lines = ["## Recommended Follow-up"]
    for task in follow_up_tasks[:5]:
        if not isinstance(task, dict):
            continue
        objective = _string_field(task, "objective")
        if objective:
            lines.append(f"- {objective}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _recommended_follow_up(latest_review: dict[str, object] | None, state: AgentState | None = None) -> list[str]:
    if latest_review is None:
        return ["Run an evidence-quality check before treating this as a final report."]
    follow_up_tasks = latest_review.get("follow_up_tasks")
    if not isinstance(follow_up_tasks, list) or not follow_up_tasks:
        notes = _string_items((state or {}).get("research_feasibility_notes"))
        return notes[:2] or ["Resolve the blocking gaps above before producing a final report."]

    follow_up = []
    allowed_domains = {normalize_domain(domain) for domain in _string_items((state or {}).get("allowed_domains"))}
    for task in follow_up_tasks[:5]:
        if not isinstance(task, dict):
            continue
        focused_domains = {normalize_domain(domain) for domain in _string_items(task.get("focused_domains"))}
        if allowed_domains and focused_domains and not focused_domains.issubset(allowed_domains):
            follow_up.append("Broaden the allowed source domains before pursuing unavailable evidence.")
            continue
        objective = _public_report_text(_string_field(task, "objective"))
        if objective:
            follow_up.append(objective)
    return _unique_strings(follow_up) or ["Resolve the blocking gaps above before producing a final report."]


def _evidence_reviewed_section(state: AgentState) -> str:
    source_count = len([source for source in state.get("research_sources", []) if isinstance(source, dict)])
    evidence_count = len([artifact for artifact in state.get("evidence_artifacts", []) if isinstance(artifact, dict)])
    read_count = len([record for record in state.get("evidence_read_records", []) if isinstance(record, dict)])
    facts = []
    if source_count:
        facts.append(f"{source_count} retained sources")
    if evidence_count:
        facts.append(f"{evidence_count} evidence artifacts")
    if read_count:
        facts.append(f"{read_count} targeted evidence reads")
    if not facts:
        return ""
    return "## Evidence Reviewed\n- " + "; ".join(facts) + "."


def _evidence_reviewed_text(state: AgentState) -> str | None:
    source_count = len([source for source in state.get("research_sources", []) if isinstance(source, dict)])
    evidence_count = len([artifact for artifact in state.get("evidence_artifacts", []) if isinstance(artifact, dict)])
    read_count = len([record for record in state.get("evidence_read_records", []) if isinstance(record, dict)])
    facts = []
    if source_count:
        facts.append(f"{source_count} retained sources")
    if evidence_count:
        facts.append(f"{evidence_count} evidence artifacts")
    if read_count:
        facts.append(f"{read_count} targeted evidence reads")
    return "; ".join(facts) + "." if facts else None


def _limitations_section(
    state: AgentState,
    latest_review: dict[str, object] | None,
    reviews: list[dict[str, object]],
) -> str:
    lines = ["## Evidence and Limitations"]
    source_quality = _public_source_quality_summary(_source_quality_assessments(reviews))
    if source_quality:
        lines.append(f"- {source_quality}")

    if _excluded_reference_notes(reviews):
        lines.append("- Lower-confidence, contradictory, or insufficiently supported items were omitted from the main synthesis.")

    provider_counts = state.get("search_provider_counts")
    if isinstance(provider_counts, dict) and provider_counts:
        rendered_counts = ", ".join(f"{provider}: {count}" for provider, count in sorted(provider_counts.items()))
        lines.append(f"- Search coverage used multiple providers ({rendered_counts}).")

    if len(lines) == 1:
        lines.append("- No material evidence-quality caveats were recorded.")
    return "\n".join(lines)


def _string_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _public_report_text(value: str, source_ids: set[str] | None = None) -> str:
    text = value.strip()
    if not text:
        return ""
    text = re.sub(r"/evidence/[^\s),;]+", "evidence artifact", text)
    for source_id in sorted(source_ids or set(), key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9_-]){re.escape(source_id)}(?![A-Za-z0-9_-])", "a recorded source", text)
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "should not anchor": "does not sufficiently support",
        "should not be used": "does not sufficiently support",
        "remove from the final": "exclude from the final",
        "removed from the final": "excluded from the final",
        "evaluator review": "evidence-quality check",
        "evaluator-approved": "supported by sufficient evidence",
        "review found": "the evidence has",
    }
    lowered = text.lower()
    for old, new in replacements.items():
        if old in lowered:
            text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
            lowered = text.lower()
    return text


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


def _summarize_source_quality(assessments: list[str]) -> str:
    if not assessments:
        return ""
    if len(assessments) == 1:
        return assessments[0]
    return " ".join(assessments[:2])


def _public_source_quality_summary(assessments: list[str]) -> str:
    if not assessments:
        return ""
    text = _summarize_source_quality(assessments).lower()
    if any(term in text for term in ["mixed", "weak", "caveat", "newsletter", "speculative", "lower-quality"]):
        return "Source quality is adequate but mixed; strongest claims should rest on primary company, cloud-provider, regulatory, or established business/technology sources."
    return "Source quality is adequate for a concise synthesis."


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _excluded_reference_notes(reviews: list[dict[str, object]]) -> list[str]:
    notes = []
    for review in reviews:
        notes.extend(_string_items(review.get("contradiction_notes")))
        notes.extend(_string_items(review.get("weak_or_unsupported_findings")))
    return _unique_strings(notes)


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
