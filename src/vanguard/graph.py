import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from langgraph.graph import StateGraph, START, END

from .brief import write_research_brief
from .langgraph_configuration import LangGraphConfig
from .planning import plan_research
from .report_generation import final_report_generation
from .review import review_research
from .research import conduct_research
from .state import AgentInputState, AgentState


logger = logging.getLogger(__name__)


def _state_counts(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "research_task_count": len(state.get("research_tasks", []) or []),
        "finding_count": len(state.get("research_findings", []) or []),
        "source_count": len(state.get("research_sources", []) or []),
        "evidence_artifact_count": len(state.get("evidence_artifacts", []) or []),
        "review_count": len(state.get("research_reviews", []) or []),
        "has_final_report": bool(state.get("final_report")),
        "status": state.get("status"),
    }


def _with_state_logging(name: str, node: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(node)
    async def wrapped(state: AgentState, *args, **kwargs):
        result = node(state, *args, **kwargs)
        if isinstance(result, Awaitable):
            result = await result
        merged = dict(state)
        if isinstance(result, dict):
            for key, value in result.items():
                existing = merged.get(key)
                if isinstance(value, list) and isinstance(existing, list):
                    merged[key] = existing + value
                else:
                    merged[key] = value
        logger.info("State after node", extra={"node": name, **_state_counts(merged)})
        return result

    return wrapped

builder = StateGraph(
    AgentState,
    context_schema=LangGraphConfig,
    input_schema=AgentInputState,
)
builder.add_node("write_research_brief", _with_state_logging("write_research_brief", write_research_brief))
builder.add_node("plan_research", _with_state_logging("plan_research", plan_research))
builder.add_node("conduct_research", _with_state_logging("conduct_research", conduct_research))
builder.add_node("review_research", _with_state_logging("review_research", review_research))
builder.add_node("final_report_generation", _with_state_logging("final_report_generation", final_report_generation))

builder.add_edge(START, "write_research_brief")
builder.add_edge("write_research_brief", "plan_research")
builder.add_edge("plan_research", "conduct_research")
builder.add_edge("conduct_research", "review_research")
builder.add_edge("review_research", "final_report_generation")
builder.add_edge("final_report_generation", END)

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    graph = builder.compile()
    result = await graph.ainvoke(
        {
            "research_intent": "Research LangGraph for deep research agents",
        },
        context=LangGraphConfig(),
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
