"""Prompts for report generation."""

FINAL_REPORT_PROMPT = """Draft a substantive narrative technical trend-scouting report draft with overview paragraphs that explain what the source evidence collectively says.
Treat the report_bundle as authoritative. Use only bundle.findings, bundle.sources, bundle.required_topics, bundle.coverage_gaps, bundle.contradiction_notes, and bundle.methodology_caveats. Do not invent facts, citations, or source IDs.
If the request includes a date window, do not cite sources with visible/published dates that clearly fall outside that window; sources with no visible/published date may still be cited when otherwise relevant and credible.
For Deep Dive, focus on the most relevant technology for the report; relevance can be interpreted as the technology that appears most frequently or prominently in selected findings.
Do not include internal source IDs, numeric citations, or parenthetical title-citation lists in prose; the renderer will attach direct source URLs.
Prefer claim-level citations: fill paragraphs and cited_bullets with source_ids close to the claim they support. Use only source IDs present in bundle.sources.
Hedge findings marked status=caution, especially findings produced by repair_research, and surface material methodology_caveats in limitations.
Summary should contain 2-3 developed paragraphs, not short blurbs or bullets. Each paragraph should synthesize multiple findings/sources into an overview of the trend, evidence direction, and implication.
Why It Matters must distinguish the selected Lance from the company overall: populate why_it_matters.for_lance and why_it_matters.for_firm. Refer to the broader organization as "the company", not "the IT consulting firm".
Why It Matters paragraphs should be developed explanatory paragraphs, not one-sentence bullets.
Trending Technologies should contain 4-5 named technologies or themes when possible. Write each item as a substantive 2-3 sentence prose mini-synthesis of what the sources indicate, not a short label and not a bullet fragment.
Deep Dive should be a coherent multi-paragraph narrative overview of the most important theme/technology, explaining what the sources collectively say, where they agree, where evidence is weaker, and what that means for spatial-computing adoption. Do not make Deep Dive a list of disconnected finding summaries.
Team Suggestions should populate team_suggestions as structured pilot/action records. Do not put URLs in pilot, dependencies, risk_and_mitigations, or success_metric. Use relative target_timing rather than inventing exact dates.
Avoid bullet-list prose outside Team Suggestions data and the renderer-owned Selected Sources list. Analytical sections should be paragraph-first narrative prose.
Avoid uncited major claims in summary or key takeaways.
Avoid pipeline/meta phrasing such as "research coverage is sufficient", "final report", "retrieved evidence", "allowed sources", "source set", "the final report should", internal source IDs like S8, and "I found".

Research intent:
{research_intent}

Selected Lance context:
{selected_lance}

Report status:
{report_status}

If report_status is partial, write only what the selected evidence supports, preserve explicit gaps and caveats, and do not imply full system or market coverage.

bundle.findings:
{bundle_findings}

bundle.sources:
{bundle_sources}

bundle.required_topics:
{required_topics}

bundle.coverage_gaps:
{coverage_gaps}

bundle.contradiction_notes:
{contradiction_notes}

bundle.methodology_caveats:
{methodology_caveats}
"""
