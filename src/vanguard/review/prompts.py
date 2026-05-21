"""Prompts for research review."""


REVIEW_RESEARCH_PROMPT = """Evaluate whether the research is sufficient for final report generation. Check coverage, source quality, contradictions, weak or unsupported findings, duplicates, stale/superseded items, and control/meta findings, and whether planned target_terms were covered. If follow-up is needed, propose only targeted bounded tasks. Apply higher scrutiny to recent, numerical, market/financial, predictive, or disputed claims. Prefer primary, official, regulatory, academic, and established expert sources; treat aggregators, feeds, low-context indexes, and speculative commentary as weaker support unless corroborated. Do not mark research sufficient just because sources exist: the retained findings must answer the brief with source_ids that support the claims. If a requested date window is present, do not select or recommend citing sources with visible/published dates that clearly fall outside that window; sources with no visible/published date may still be selected when otherwise relevant and credible. Set core_brief_answerable=false only when no caveated answer to the core brief is supportable from available evidence; if evidence supports a limited report with explicit gaps, leave core_brief_answerable true or unset and describe those gaps. Weakness notes are control data for filtering, not user-facing findings. Prefer follow-up findings when they resolve earlier uncertainty and supersede older conflicts. Feasibility notes describe source constraints that may make parts of the brief impossible under current runtime policy. Populate required_report_topics with important source-supported targets/dimensions the final report should cover. Populate coverage_gaps with important target_terms/topics that remain missing, weakly supported, or undercovered; if the research is still sufficient, these gaps should be caveats rather than blockers. Follow-up tasks must stay within current allowed_domains; never propose tasks requiring unavailable domains. If a gap requires unavailable domains, state that in coverage/source-quality assessment or coverage_gaps rather than proposing an unreachable task. For follow-up tasks with focused domains, write objectives, key questions, target_terms, and expected output using source-native query angles that imply what to search for on those domains; avoid generic entity-only wording. Do not ask follow-up workers to use site:, domain names, OR chains, or other search-engine syntax because domain restrictions are enforced by runtime policy. Request raw evidence reads for high-value sources that need deeper inspection for validation or final report synthesis. Choose sources by source_id from research_sources; Python will resolve the source_id to its known raw_content_path. Do not request arbitrary paths and do not ask to read all evidence. Populate selected_report_sources with use/caution/exclude decisions for sources relevant to final report synthesis; include only known source_id values from research_sources. Also populate selected_report_findings with use/caution/exclude decisions for finding_id values provided by Python.

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
