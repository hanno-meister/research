"""Default providers for the research agent search tool."""

from vanguard.research.search_gateway import ExaSearchAdapter, SearchGateway, TavilySearchAdapter


MAX_SEARCH_CALLS_PER_WORKER = 2
INITIAL_SEARCH_RESULTS_PER_PROVIDER = 10
FOLLOW_UP_SEARCH_RESULTS_PER_PROVIDER = 5


def default_search_gateway(*, results_per_provider: int = INITIAL_SEARCH_RESULTS_PER_PROVIDER) -> SearchGateway:
    return SearchGateway(
        [
            ExaSearchAdapter(num_results=results_per_provider, highlights_max_characters=1_000),
            TavilySearchAdapter(
                max_results=results_per_provider,
                search_depth="advanced",
                include_raw_content="markdown",
            ),
        ]
    )
