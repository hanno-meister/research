"""Search policy and query derivation for research runs."""

from datetime import date

from typing import Any

from vanguard.research.search_gateway_models import SearchPolicy
from vanguard.state import AgentState
from vanguard.utils.urls import normalize_search_query

from .models import ResearchAgentContext, ResearchSearchBudget
from .recorder import ResearchRunRecorder


def search_context_from_state(
    state: AgentState,
    research_brief: str,
    filesystem_backend: Any,
    recorder: ResearchRunRecorder,
    *,
    default_query: str | None = None,
    default_highlight_query: str | None = None,
    focused_domains: tuple[str, ...] = (),
    task_id: str | None = None,
    search_budget: ResearchSearchBudget | None = None,
) -> ResearchAgentContext:
    return ResearchAgentContext(
        search_policy=_search_policy_from_state(state),
        default_query=default_query or _search_query_from_state(state, research_brief),
        default_highlight_query=default_highlight_query or research_brief,
        focused_domains=focused_domains,
        task_id=task_id,
        search_budget=search_budget or ResearchSearchBudget(max_search_calls=1),
        filesystem_backend=filesystem_backend,
        recorder=recorder,
    )


def _search_query_from_state(state: AgentState, research_brief: str) -> str:
    return normalize_search_query(state.get("research_intent") or research_brief)


def _search_policy_from_state(state: AgentState) -> SearchPolicy:
    return SearchPolicy(
        allowed_domains=tuple(state.get("allowed_domains", ())),
        start_date=_optional_date(state.get("start_date")),
        end_date=_optional_date(state.get("end_date")),
    )


def _optional_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)
