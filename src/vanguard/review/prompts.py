"""Prompts for research review."""


REVIEW_RESEARCH_PROMPT = """Evaluate whether the research is sufficient for final report generation. Check coverage, source quality, contradictions, and weak or unsupported findings. If follow-up is needed, propose only targeted bounded tasks. Apply higher scrutiny to recent, numerical, market/financial, predictive, or disputed claims. Prefer primary, official, regulatory, academic, and established expert sources; treat aggregators, feeds, low-context indexes, and speculative commentary as weaker support unless corroborated. Do not mark research sufficient just because sources exist: the retained findings must answer the brief with source_ids that support the claims. Weakness notes are control data for filtering, not user-facing findings. Feasibility notes describe source constraints that may make parts of the brief impossible under current runtime policy. Follow-up tasks must stay within current allowed_domains; never propose tasks requiring unavailable domains. If a gap requires unavailable domains, state that in coverage/source-quality assessment rather than proposing an unreachable task. For follow-up tasks with focused domains, write objectives, key questions, and expected output using source-native query angles that imply what to search for on those domains; avoid generic entity-only wording. Do not ask follow-up workers to use site:, domain names, OR chains, or other search-engine syntax because domain restrictions are enforced by runtime policy. Request raw evidence reads for high-value sources that need deeper inspection for validation or final report synthesis. Choose sources by source_id from research_sources; Python will resolve the source_id to its known raw_content_path. Do not request arbitrary paths and do not ask to read all evidence. Populate selected_report_sources with use/caution/exclude decisions for sources relevant to final report synthesis; include only known source_id values from research_sources.

Review round: {round_number}
Research brief:
{research_brief}

Original tasks:
{research_tasks}

Findings:
{research_findings}

Sources:
{research_sources}

Evidence artifacts:
{evidence_artifacts}

Feasibility notes:
{research_feasibility_notes}

Diversity notes:
{source_diversity_notes}

Provider counts: {search_provider_counts}
Domain counts: {search_domain_counts}

Selected evidence snippets already read:
{evidence_snippets}"""
