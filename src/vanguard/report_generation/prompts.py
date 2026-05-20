"""Prompts for report generation."""

FINAL_REPORT_PROMPT = """Draft a concise section-level synthesis.
Treat the latest review as authoritative. Follow-up findings supersede older conflicts when they resolve uncertainty.
Use only the provided findings and review metadata. Do not invent facts, citations, or source IDs.
For Deep Dive, focus on the most relevant technology for the report; relevance can be interpreted as the technology that appears most frequently or prominently in selected findings.
Do not include internal source IDs, numeric citations, or parenthetical title-citation lists in prose; the renderer will attach direct source URLs.
For Summary, Why It Matters, Trending Technologies, and Team Suggestions, attach selected source_ids to each section or bullet so the renderer can add direct source URLs. Use only reviewed selected source IDs.
Avoid uncited major claims in summary or key takeaways.
Avoid pipeline/meta phrasing such as "research coverage is sufficient", "final report", "retrieved evidence", "allowed sources", "source set", "the final report should", internal source IDs like S8, and "I found".

Research intent:
{research_intent}

Selected Lance context:
{selected_lance}

Findings:
{research_findings}

Review metadata:
{research_reviews}

Required report topics from review:
{required_report_topics}

Coverage gaps from review:
{coverage_gaps}

Selected sources:
{selected_report_sources}
"""
