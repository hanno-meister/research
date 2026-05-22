"""LangChain research agent construction."""

from pathlib import Path
from typing import Any

from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from vanguard.langgraph_configuration import LangGraphConfig

from .models import ResearchAgentContext, ResearchAgentOutput
from .tools import search_gateway


REPO_ROOT = Path(__file__).parents[3]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / ".vanguard"


RESEARCH_AGENT_SYSTEM_PROMPT = """You are a constrained research worker inside a larger LangGraph workflow.

Rules:
- Use the search_gateway tool for source discovery. Do not invent sources.
- The search_gateway tool stores raw evidence and returns compact metadata plus evidence paths.
- Prefer primary, official, regulatory, academic, or established expert sources when available; use aggregators, indexes, feeds, or speculative commentary only with explicit caveats.
- Treat recency, dates, market reaction, forecasts, and numerical claims as high-risk: verify them against the strongest available sources and state uncertainty when support is limited.
- Cite findings only with source_ids returned by the tool. Do not cite URLs, paths, or source_ids that were not returned to you.
- Do not convert review/control notes into findings. Findings should be user-facing factual synthesis only.
- If the task cannot be answered well under the available source constraints, say so in a compact finding instead of overstating evidence.
- Keep returned findings compact. Never include raw source content in the structured response.
- Return only synthesis fields. Source metadata, evidence artifacts, provider counts, and domain counts are tracked automatically.
- Return structured output only.
"""


def create_research_agent(config: LangGraphConfig, backend: CompositeBackend | None = None):
    backend = backend or filesystem_backend_for_config(config)
    model = ChatOpenAI(
        model=config.small_model,
        base_url=config.openai_base_url,
        api_key=config.azure_openai_api_key,
        use_responses_api=False,
    )
    return create_agent(
        model=model,
        tools=[search_gateway],
        middleware=[FilesystemMiddleware(backend=backend)],
        response_format=ResearchAgentOutput,
        context_schema=ResearchAgentContext,
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT,
    )


def filesystem_backend_for_config(config: Any | None = None) -> CompositeBackend:
    configured_root = getattr(config, "evidence_root", None)
    evidence_root = Path(configured_root) if configured_root else DEFAULT_EVIDENCE_ROOT
    if not evidence_root.is_absolute():
        evidence_root = REPO_ROOT / evidence_root
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/evidence/": FilesystemBackend(
                root_dir=evidence_root,
                virtual_mode=True,
            )
        },
    )
