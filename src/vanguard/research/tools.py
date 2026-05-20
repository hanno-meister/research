"""Tools exposed to the LangChain research agent."""

import logging
from typing import Any

from langchain.tools import ToolRuntime, tool
from vanguard.utils.urls import (
    allowed_url_target_contains_target,
    normalize_allowed_url_targets,
    normalize_search_query,
)

from .defaults import default_search_gateway
from .evidence import write_evidence_file
from .models import ResearchAgentContext


logger = logging.getLogger(__name__)


@tool
async def search_gateway(
    runtime: ToolRuntime[ResearchAgentContext],
    query: str | None = None,
    highlight_query: str | None = None,
) -> dict[str, Any]:
    """Search Exa and Tavily through the constrained gateway.

    Use this for web/source discovery. Hard policy constraints are injected at
    runtime and enforced by the gateway; do not call external search providers directly.
    """

    return await _run_search_gateway_tool(query, highlight_query, runtime.context)


async def _run_search_gateway_tool(
    query: str | None,
    highlight_query: str | None,
    context: ResearchAgentContext,
) -> dict[str, Any]:
    if not await context.search_budget.reserve_search_call():
        logger.info(
            "Search gateway budget exhausted",
            extra={
                "task_id": context.task_id,
                "max_search_calls": context.search_budget.max_search_calls,
            },
        )
        return {
            "error": (
                f"Search budget exhausted for task {context.task_id or 'unknown'}; "
                f"maximum {context.search_budget.max_search_calls} calls allowed."
            ),
            "results": [],
            "evidence_artifacts": [],
            "provider_counts": {},
            "domain_counts": {},
            "duplicates_removed": 0,
        }

    resolved_query = normalize_search_query(query or "")
    if not resolved_query:
        return {
            "error": "search_gateway requires a non-empty query.",
            "results": [],
            "evidence_artifacts": [],
            "provider_counts": {},
            "domain_counts": {},
            "duplicates_removed": 0,
        }
    resolved_highlight_query = normalize_search_query(highlight_query or resolved_query)
    focused_domains = _sanitize_focused_domains(context.focused_domains, context.search_policy.allowed_url_targets)
    logger.info(
        "Running search gateway tool",
        extra={
            "model_query": query,
            "model_highlight_query": highlight_query,
            "resolved_query": resolved_query,
            "allowed_domains": context.search_policy.allowed_domains,
            "start_date": context.search_policy.start_date.isoformat()
            if context.search_policy.start_date
            else None,
            "end_date": context.search_policy.end_date.isoformat()
            if context.search_policy.end_date
            else None,
        },
    )
    result = await _search_gateway_for_context(context).search(
        query=resolved_query,
        policy=context.search_policy,
        focused_domains=focused_domains,
        highlight_query=resolved_highlight_query,
    )
    evidence_by_url = {
        item.normalized_url: artifact
        for item in result.results
        if (artifact := write_evidence_file(item, context.filesystem_backend)) is not None
    }
    serialized_results = [
        _serialize_search_result(item, evidence_by_url.get(item.normalized_url))
        for item in result.results
    ]
    evidence_artifacts = list(evidence_by_url.values())
    recorded_results = context.recorder.record_search_results(serialized_results, evidence_artifacts)
    response = {
        "results": recorded_results,
        "evidence_artifacts": evidence_artifacts,
        "provider_counts": result.provider_counts,
        "domain_counts": result.domain_counts,
        "provider_errors": [
            {
                "provider": error.provider,
                "error_type": error.error_type,
                "message": error.message,
            }
            for error in result.provider_errors
        ],
        "duplicates_removed": len(result.duplicates),
    }
    logger.info(
        "Search gateway tool completed",
        extra={
            "result_count": len(result.results),
            "evidence_artifact_count": len(evidence_by_url),
            "duplicates_removed": len(result.duplicates),
            "provider_counts": result.provider_counts,
            "domain_counts": result.domain_counts,
            "provider_errors": [error.provider for error in result.provider_errors],
        },
    )
    return response


def _search_gateway_for_context(context: ResearchAgentContext):
    try:
        return default_search_gateway(results_per_provider=context.results_per_provider)
    except TypeError:
        return default_search_gateway()


def _sanitize_focused_domains(
    focused_domains: tuple[str, ...],
    allowed_url_targets,
) -> tuple[str, ...]:
    if not focused_domains:
        return ()
    normalized_targets = normalize_allowed_url_targets(focused_domains)
    if not normalized_targets:
        return ()
    valid_targets = [
        target
        for target in normalized_targets
        if any(allowed_url_target_contains_target(allowed, target) for allowed in allowed_url_targets)
    ]
    return tuple(target.domain for target in valid_targets)


def _serialize_search_result(item, evidence_artifact=None) -> dict[str, str | None]:
    return {
        "provider": item.provider,
        "query": item.query,
        "url": item.url,
        "title": item.title,
        "summary": item.summary,
        "raw_content_path": evidence_artifact["path"] if evidence_artifact else None,
        "published_date": item.published_date,
        "normalized_url": item.normalized_url,
        "canonical_domain": item.canonical_domain,
    }
