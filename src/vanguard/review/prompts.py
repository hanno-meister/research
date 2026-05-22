"""Prompts for research review."""


_REVIEW_CONTEXT = """
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


# TODO:Use structured output
REVIEW_TRIAGE_PROMPT = """You are the triage pass of a two-pass research review. Your only job is to select which evidence files the final reviewer should read in full before making their judgment.

Output evidence_to_read as a ranked list of at most {max_evidence_reads} source_ids, most important first, with a one-line reason per selection.

Select sources where reading raw content would change a decision the final reviewer must make. Strong candidates:
- Sources whose summaries make load-bearing factual or numerical claims that are the primary or only support for required-coverage topics from the research brief
- Sources flagged with warnings, or whose type suggests low context: search index pages, author pages, feed/index pages, or aggregators
- Sources with a summary that is too thin, vague, or high-level to verify whether the finding's specific claim is actually present
- Sources where the published date or URL suggests a possible date-window mismatch with the requested window
- Sources that are the sole citation for a finding on a required named target (e.g. a specific product, system, or benchmark named in the brief)

Deprioritize sources that are clearly supplementary, redundant with stronger evidence already in the corpus, or whose summary already contains enough detail to evaluate the claim confidently.

Do not assess overall coverage. Do not evaluate source quality beyond triage-level suspicion flags. Do not identify contradictions. Do not assess whether findings are weak or unsupported. Do not propose follow-up tasks. Do not write any notes about the research being sufficient or insufficient. Those are the final reviewer's job.

Output only:
- evidence_to_read: ranked list of source_ids with one-line reasons
- triage_notes: a short list of any suspicion flags worth flagging to the final reviewer (e.g. "S79 appears to be an arXiv search index page, verify date and source type before using for primary claims"). Leave empty if nothing flagged.
""" + _REVIEW_CONTEXT


REVIEW_FINAL_PROMPT = """You are the final pass of a two-pass research review. Triage has already selected evidence files for reading, and their raw content is included in the context below alongside triage_notes flagging any suspicion points. Use the raw content and triage notes to inform your judgment.

Your job is to make the sufficiency judgment, filter findings and sources for the report bundle, and decide whether repair research is needed.

Evaluate all of the following:
- Coverage of the research brief and required target terms
- Whether retained findings actually answer the brief, not just whether sources exist
- Source quality: apply higher scrutiny to recent, numerical, market/financial, predictive, or disputed claims; prefer primary, official, regulatory, academic, and established expert sources; treat aggregators, feeds, low-context indexes, and speculative commentary as weaker support unless corroborated
- Contradictions between findings or between findings and raw evidence you read
- Weak or unsupported findings: a finding is weak if its cited source_ids do not actually contain the claimed information, or if the sources are out-of-window, low-context, or flagged by triage
- Duplicates and near-duplicates across sources and findings
- Stale or superseded items, especially where a repair round produced newer evidence that resolves an earlier conflict
- Control and meta findings that describe search failures or task-execution issues and should not surface to the user as substantive findings

Cross-task coherence: evaluate whether findings from different tasks build on each other where the evidence supports it, or whether they remain parallel silos that restate similar evidence without integration. When findings from one task contain evidence that would strengthen or qualify a finding from another task, flag this as a synthesis gap in coverage_assessment so the final report generator can address it. This is not grounds for repair research — it is a signal that the evidence is present but underconnected and should be surfaced to the reader.

Gap-to-consequence linkage: when identifying coverage gaps in coverage_assessment, tie each gap to what it blocks — a specific recommendation, decision, or strategic question that cannot be made with confidence until the gap is closed. A gap with no consequence is either not material or is missing the analysis of why it matters; in either case, either supply the consequence or remove the gap from the assessment. Gaps that block nothing actionable should not be carried forward to the report bundle.

Date-window handling: if a requested date window is present, do not select or recommend citing sources with visible published dates or URL identifiers that clearly fall outside that window. Sources with no visible date may be selected when otherwise credible and relevant, but must be labeled as undated. When raw content you read confirms a source is out-of-window or low-context (e.g. an arXiv search index page containing abstracts from outside the window), exclude it and walk back any findings whose support collapses as a result, including findings that were not directly cited by that source but depended on it for a claim chain.

Sufficiency rules:
- Do not mark research sufficient just because sources exist. Retained findings must answer the brief with source_ids that actually support the claims.
- Set core_brief_answerable=false only when no caveated answer to the core brief is supportable from the available evidence. If evidence supports a limited report with explicit gaps, leave core_brief_answerable true and describe the gaps in coverage_assessment.
- If sufficient=false and core_brief_answerable=true, you must populate follow_up_tasks. Leaving follow_up_tasks empty when the brief is answerable but evidence is incomplete is a review error: it routes to final report generation instead of repair.

Follow-up task rules:
- Generate at most {max_follow_up_tasks} follow-up tasks.
- Order strictly by priority so the most critical task runs first if the budget is exceeded.
- All follow-up tasks must have depends_on: [] unless a second repair cycle is explicitly confirmed available in this pipeline. Tasks with non-empty depends_on will be silently dropped in a single-repair-cycle pipeline.
- Prefer follow-up tasks that resolve earlier uncertainty or supersede older conflicting findings rather than expanding scope.

Weakness notes are control data for bundle filtering, not user-facing findings. Write them precisely so the bundle builder can act on them accurately.
""" + _REVIEW_CONTEXT


REVIEW_RESEARCH_PROMPT = REVIEW_FINAL_PROMPT
