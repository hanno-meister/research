import asyncio
import logging

from langgraph.graph import StateGraph, START, END

from .brief import write_research_brief
from .langgraph_configuration import LangGraphConfig
from .report import final_report_generation
from .research import conduct_research
from .state import AgentInputState, AgentState

builder = StateGraph(
    AgentState,
    context_schema=LangGraphConfig,
    input_schema=AgentInputState,
)
builder.add_node("write_research_brief", write_research_brief)
builder.add_node("conduct_research", conduct_research)
builder.add_node("final_report_generation", final_report_generation)

builder.add_edge(START, "write_research_brief")
builder.add_edge("write_research_brief", "conduct_research")
builder.add_edge("conduct_research", "final_report_generation")
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
