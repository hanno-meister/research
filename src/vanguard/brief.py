"""Research brief generation node."""

import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from .contracts import ResearchQuestion
from .langgraph_configuration import LangGraphConfig
from .prompts import RESEARCH_BRIEF_PROMPT
from .state import AgentState


logger = logging.getLogger(__name__)


async def write_research_brief(state: AgentState, runtime: Runtime[LangGraphConfig]):
    logger.info("Generating research brief", extra={"research_intent": state["research_intent"]})
    model = ChatOpenAI(
        model=runtime.context.small_model,
        base_url=runtime.context.openai_base_url,
        api_key=runtime.context.azure_openai_api_key,
        use_responses_api=False,
    )
    structured_model = model.with_structured_output(ResearchQuestion)
    response = await structured_model.ainvoke(
        [
            HumanMessage(
                content=RESEARCH_BRIEF_PROMPT.format(
                    research_intent=state["research_intent"],
                    selected_lance=_selected_lance_text(state),
                )
            )
        ]
    )

    if not isinstance(response, ResearchQuestion):
        raise TypeError(f"Expected ResearchQuestion, got {type(response).__name__}")

    logger.info("Generated research brief", extra={"research_brief_characters": len(response.research_brief)})
    return {"research_brief": response.research_brief}


def _selected_lance_text(state: AgentState) -> str:
    lance = state.get("selected_lance") or {}
    if not isinstance(lance, dict):
        return "none"
    parts = [
        f"id: {str(lance.get('id', '')).strip()}",
        f"name: {str(lance.get('name', '')).strip()}",
        f"description: {str(lance.get('description', '')).strip()}",
    ]
    text = "\n".join(part for part in parts if not part.endswith(": "))
    return text or "none"
