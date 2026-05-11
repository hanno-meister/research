"""Research graph node implementations."""

from .search_gateway import (
    ExaSearchAdapter,
    NormalizedSearchResult,
    SearchGateway,
    SearchPolicy,
    source_diversity_note,
    TavilySearchAdapter,
)
from .state import AgentState

MAX_SEARCH_QUERY_CHARACTERS = 400


async def conduct_research(state: AgentState):
    research_brief = state.get("research_brief")
    if not research_brief:
        raise ValueError("Missing research_brief. Did write_research_brief run?")

    search_query = _search_query_from_state(state, research_brief)
    gateway = _default_search_gateway()
    search_result = await gateway.search(
        query=search_query,
        policy=SearchPolicy(),
        highlight_query=research_brief,
    )

    diversity_note = source_diversity_note(search_result.results)

    return {
        "research_findings": [_format_search_findings(search_result.results)],
        "research_sources": [_serialize_source(result) for result in search_result.results],
        "source_diversity_notes": [diversity_note] if diversity_note else [],
        "search_provider_counts": search_result.provider_counts,
        "search_domain_counts": search_result.domain_counts,
    }


def _default_search_gateway() -> SearchGateway:
    return SearchGateway(
        [
            ExaSearchAdapter(num_results=5, highlights_max_characters=1_000),
            TavilySearchAdapter(
                max_results=5,
                search_depth="advanced",
                include_raw_content=False,
            ),
        ]
    )


def _search_query_from_state(state: AgentState, research_brief: str) -> str:
    query = state.get("research_intent") or research_brief
    query = " ".join(query.split())
    if len(query) <= MAX_SEARCH_QUERY_CHARACTERS:
        return query
    return query[:MAX_SEARCH_QUERY_CHARACTERS].rsplit(" ", 1)[0]


def _format_search_findings(results: list[NormalizedSearchResult]) -> str:
    if not results:
        return "No search results were returned."

    findings: list[str] = []
    for index, result in enumerate(results, start=1):
        title = result.title or result.url
        summary = result.summary or "No provider summary available."
        findings.append(
            f"[{index}] {title}\n"
            f"Source: {result.url}\n"
            f"Provider: {result.provider}\n"
            f"Summary: {summary}"
        )
    return "\n\n".join(findings)


def _serialize_source(result: NormalizedSearchResult) -> dict[str, str | None]:
    return {
        "provider": result.provider,
        "query": result.query,
        "url": result.url,
        "title": result.title,
        "summary": result.summary,
        "published_date": result.published_date,
        "normalized_url": result.normalized_url,
        "canonical_domain": result.canonical_domain,
    }
