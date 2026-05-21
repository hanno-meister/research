"""Prompts for bounded research worker agents."""

RESEARCH_WORKER_TASK_PROMPT = """Conduct bounded research for exactly one focused task. Use the search_gateway tool, cite only source_id values and raw_content_path values returned by the tool, and return only compact structured findings and diversity notes. Stay within the task objective and boundaries; do not research unrelated plan tasks. Do not return source lists, evidence artifacts, provider counts, or domain counts; those are tracked automatically. You have a hard budget of {search_call_budget} search_gateway calls for this task.

Search query rules:
- Keep each search_gateway query concise and provider-safe: use a focused keyword-style query under 400 characters rather than pasting the full brief or task text.
- Do not include site:, domain names, OR chains, quoted boolean expressions, or search-engine syntax. Domain restrictions are already enforced by runtime policy.
- Date restrictions are also enforced by runtime policy. Treat dated sources that clearly fall outside the requested date window as non-qualifying; sources with no visible/published date may still be used when otherwise relevant and credible.
- Use source-native topic terms likely to appear in result titles/snippets. For official vendor blogs, use product/ecosystem terms; for arXiv, use technical method, benchmark, and paper-title terms; for expert/news sources, use product names plus launch/capability terms.
- When this task has focused_domains, adapt the query vocabulary to what those domains likely publish. Do not use generic entity-only queries; combine the entity/system with task-specific concepts and source-appropriate terms.
- Explicitly check the task's target_terms across your limited search budget. Combine target terms with the task objective and source-native capability or benchmark terms.

Research brief:
{research_brief}

Focused worker task:
{worker_task_text}"""
