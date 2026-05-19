"""Default providers for the research agent search tool."""

from vanguard.research.search_gateway import ExaSearchAdapter, SearchGateway, TavilySearchAdapter


MAX_SEARCH_CALLS_PER_WORKER = 2


def default_search_gateway() -> SearchGateway:
    return SearchGateway(
        [
            ExaSearchAdapter(num_results=5, highlights_max_characters=1_000),
            TavilySearchAdapter(
                max_results=5,
                search_depth="advanced",
                include_raw_content="markdown",
            ),
        ]
    )
