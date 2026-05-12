"""Final report generation node."""

from .state import AgentState


def final_report_generation(state: AgentState):
    findings = "\n".join(_finding_text(finding) for finding in state.get("research_findings", []))
    diversity_notes = "\n".join(state.get("source_diversity_notes", []))
    if diversity_notes:
        findings = f"{findings}\n\n{diversity_notes}"
    return {"final_report": f"Final report:\n\n{findings}"}


def _finding_text(finding: object) -> str:
    if isinstance(finding, str):
        return finding
    if not isinstance(finding, dict):
        return str(finding)

    summary = str(finding.get("summary") or "")
    source_ids = finding.get("source_ids") or []
    evidence_paths = finding.get("evidence_paths") or []
    refs = []
    if source_ids:
        refs.append(f"sources: {', '.join(str(source_id) for source_id in source_ids)}")
    if evidence_paths:
        refs.append(f"evidence: {', '.join(str(path) for path in evidence_paths)}")
    if refs:
        return f"{summary} ({'; '.join(refs)})"
    return summary
