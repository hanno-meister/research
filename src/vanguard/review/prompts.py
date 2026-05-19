"""Prompt construction for research review."""

from vanguard.state import AgentState


def review_prompt(
    state: AgentState,
    *,
    round_number: int,
    evidence_snippets: list[dict[str, str | int]],
) -> str:
    return (
        "Evaluate whether the research is sufficient for final report generation. "
        "Check coverage, source quality, contradictions, and weak or unsupported "
        "findings. If follow-up is needed, propose only targeted bounded tasks. "
        "Apply higher scrutiny to recent, numerical, market/financial, predictive, "
        "or disputed claims. Prefer primary, official, regulatory, academic, and "
        "established expert sources; treat aggregators, feeds, low-context indexes, "
        "and speculative commentary as weaker support unless corroborated. "
        "Do not mark research sufficient just because sources exist: the retained "
        "findings must answer the brief with source_ids that support the claims. "
        "Weakness notes are control data for filtering, not user-facing findings. "
        "Feasibility notes describe source constraints that may make parts of the "
        "brief impossible under current runtime policy. When proposing follow-up, "
        "prefer tasks that can be completed within current allowed_domains. If a "
        "gap requires unavailable domains, state that in coverage/source-quality "
        "assessment rather than proposing an unreachable task. "
        "Request raw evidence reads only for important or uncertain sources. "
        "Choose sources by source_id from research_sources; Python will resolve the "
        "source_id to its known raw_content_path. Do not request arbitrary paths and "
        "do not ask to read all evidence.\n\n"
        f"Review round: {round_number}\n"
        f"Research brief:\n{state.get('research_brief', '')}\n\n"
        f"Original tasks:\n{state.get('research_tasks', [])}\n\n"
        f"Findings:\n{state.get('research_findings', [])}\n\n"
        f"Sources:\n{state.get('research_sources', [])}\n\n"
        f"Evidence artifacts:\n{state.get('evidence_artifacts', [])}\n\n"
        f"Feasibility notes:\n{state.get('research_feasibility_notes', [])}\n\n"
        f"Diversity notes:\n{state.get('source_diversity_notes', [])}\n\n"
        f"Provider counts: {state.get('search_provider_counts', {})}\n"
        f"Domain counts: {state.get('search_domain_counts', {})}\n\n"
        f"Selected evidence snippets already read:\n{evidence_snippets}"
    )
