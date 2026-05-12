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
        f"Diversity notes:\n{state.get('source_diversity_notes', [])}\n\n"
        f"Provider counts: {state.get('search_provider_counts', {})}\n"
        f"Domain counts: {state.get('search_domain_counts', {})}\n\n"
        f"Selected evidence snippets already read:\n{evidence_snippets}"
    )
