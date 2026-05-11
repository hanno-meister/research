import asyncio

from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .langgraph_configuration import LangGraphConfig
from .prompts import RESEARCH_BRIEF_PROMPT

from .state import (
        AgentInputState,
        AgentState,
        ResearchQuestion
)
from .research import conduct_research

async def write_research_brief(state: AgentState, runtime: Runtime[LangGraphConfig]):
    model = ChatOpenAI(
        model=runtime.context.small_model,
        base_url=runtime.context.openai_base_url,
        api_key=runtime.context.azure_openai_api_key,
        use_responses_api=False,
    )

    structured_model = model.with_structured_output(ResearchQuestion)

    prompt = RESEARCH_BRIEF_PROMPT.format(
        research_intent=state["research_intent"]
    )
    response = await structured_model.ainvoke([
        HumanMessage(content=prompt)
    ])

    if not isinstance(response, ResearchQuestion):
        raise TypeError(f"Expected ResearchQuestion, got {type(response).__name__}")

    return {
        "research_brief": response.research_brief
    }
def final_report_generation(state: AgentState):
    findings = "\n".join(state.get("research_findings", []))
    diversity_notes = "\n".join(state.get("source_diversity_notes", []))
    if diversity_notes:
        findings = f"{findings}\n\n{diversity_notes}"
    return {
        "final_report": f"Final report:\n\n{findings}"
    }

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
