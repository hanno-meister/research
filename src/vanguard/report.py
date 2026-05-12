"""Final report generation node."""

from .state import AgentState


def final_report_generation(state: AgentState):
    findings = "\n".join(state.get("research_findings", []))
    diversity_notes = "\n".join(state.get("source_diversity_notes", []))
    if diversity_notes:
        findings = f"{findings}\n\n{diversity_notes}"
    return {"final_report": f"Final report:\n\n{findings}"}
