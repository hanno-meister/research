"""LangGraph node implementation for research."""

import logging

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from vanguard.langgraph_configuration import LangGraphConfig
from vanguard.state import AgentState

from .agent import create_research_agent, filesystem_backend
from .models import ResearchAgentContext, ResearchAgentOutput
from .policy import search_context_from_state
from .recorder import ResearchRunRecorder


logger = logging.getLogger(__name__)


async def conduct_research(state: AgentState, runtime: Runtime[LangGraphConfig]):
    research_brief = state.get("research_brief")
    if not research_brief:
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    backend = filesystem_backend()
    recorder = ResearchRunRecorder()
    agent_context = search_context_from_state(state, research_brief, backend, recorder)
    logger.info(
        "Starting research agent",
        extra={
            "default_query": agent_context.default_query,
            "allowed_domains": agent_context.search_policy.allowed_domains,
            "start_date": agent_context.search_policy.start_date.isoformat()
            if agent_context.search_policy.start_date
            else None,
            "end_date": agent_context.search_policy.end_date.isoformat()
            if agent_context.search_policy.end_date
            else None,
        },
    )

    agent = create_research_agent(runtime.context, backend=backend)
    agent_result = await agent.ainvoke(
        _agent_input(research_brief),
        context=agent_context,
    )

    output = agent_result.get("structured_response")
    if not isinstance(output, ResearchAgentOutput):
        raise TypeError(f"Expected ResearchAgentOutput, got {type(output).__name__}")
    if recorder.search_attempts == 0:
        raise ValueError("Research agent completed without calling search_gateway")
    if output.findings and not recorder.sources():
        raise ValueError("Research agent produced findings without recorded sources")

    logger.info(
        "Research agent completed",
        extra={
            "finding_count": len(output.findings),
            "source_count": len(recorder.sources()),
            "evidence_artifact_count": len(recorder.evidence_artifacts()),
            "provider_counts": recorder.provider_counts(),
            "domain_counts": recorder.domain_counts(),
        },
    )
    return _state_update_from_output(output, recorder)


def _agent_input(research_brief: str) -> dict[str, list[HumanMessage]]:
    return {
        "messages": [
            HumanMessage(
                content=(
                    "Conduct research for this brief. Use the search_gateway tool, "
                    "cite the compact source metadata returned by the tool, and return "
                    "only compact structured findings and diversity notes. Do not return "
                    "source lists, evidence artifacts, provider counts, or domain counts; "
                    "those are tracked automatically.\n\n"
                    f"Research brief:\n{research_brief}"
                )
            )
        ]
    }


def _state_update_from_output(output: ResearchAgentOutput, recorder: ResearchRunRecorder):
    return {
        "research_findings": output.findings,
        "research_sources": recorder.sources(),
        "evidence_artifacts": recorder.evidence_artifacts(),
        "source_diversity_notes": output.source_diversity_notes,
        "search_provider_counts": recorder.provider_counts(),
        "search_domain_counts": recorder.domain_counts(),
    }
