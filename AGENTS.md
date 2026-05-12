# AGENTS.md

## Project shape

- Python 3.11 project managed by `uv`; update `uv.lock` with `pyproject.toml` dependency changes.
- The real app entrypoint is `src/vanguard/graph.py` (`builder` plus a `__main__` demo); root `main.py` is only a hello-world placeholder.
- `graph.py` wires `write_research_brief -> plan_research -> conduct_research -> review_research -> final_report_generation`.
- State/config/prompt contracts live in `src/vanguard/state.py`, `src/vanguard/langgraph_configuration.py`, and `src/vanguard/prompts.py`.
- `src/vanguard/search_gateway.py` is standalone Exa/Tavily provider plumbing; tests inject fake clients and must not call external search APIs.
- Research evidence is written through DeepAgents filesystem middleware under virtual `/evidence/` paths backed by local `.vanguard/` (ignored by git).

## Commands

- Install/sync dependencies: `uv sync`.
- Run all tests: `uv run pytest`.
- Run one test file: `uv run pytest tests/test_search_gateway.py`.
- Run one test: `uv run pytest tests/test_graph.py::test_search_gateway_tool_schema_hides_runtime_policy`.
- Smoke-test graph imports/compilation without an API call: `AZURE_OPENAI_API_KEY=dummy uv run python -c "from src.vanguard.graph import builder; builder.compile(); print('graph compiles')"`.
- No lint, typecheck, formatter, CI, or pre-commit config is present yet.

## Configuration and environment

- Run commands from the repo root: `config.py` opens `pyproject.toml` by relative path at import time.
- `.env` is loaded via `python-dotenv`; `.env` is ignored and must not be committed.
- Importing `LangGraphConfig`/`src.vanguard.graph` requires `AZURE_OPENAI_API_KEY`; use a dummy value only for import/compile smoke tests.
- Exa/Tavily default adapters require `EXA_API_KEY`/`TAVILY_API_KEY`; unit tests avoid these by passing fake clients.
- Model names and `openai_base_url` are configured in `[tool.vanguard]` in `pyproject.toml`, not in code.

## LangChain/LangGraph notes

- `opencode.json` enables the repo-local `langchain-docs` MCP; use it for current LangChain/LangGraph API details before changing graph code.
- `write_research_brief` uses `ChatOpenAI(..., use_responses_api=False)` with structured output `ResearchQuestion`.
- `plan_research` uses the large model with structured `ResearchPlan`; sanitized `focused_domains` must stay within `allowed_domains`, and empty/invalid plans fall back to `task-1`.
- `conduct_research` runs one bounded worker per planned task; each worker must call `search_gateway` and has `MAX_SEARCH_CALLS_PER_WORKER = 2`.
- `create_research_agent` uses `create_agent(..., response_format=ResearchAgentOutput)` plus `FilesystemMiddleware`; worker findings cite recorder-owned `source_id` and `/evidence/...` paths, not raw content.
- `review_research` can read only known `/evidence/...` artifacts, stores read records without snippet content, and caps review/follow-up work in `src/vanguard/review/defaults.py`.
- Additive `AgentState` fields (`research_findings`, `research_sources`, `evidence_artifacts`, `source_diversity_notes`, `research_reviews`, `evidence_read_records`) must be returned as lists to append, not scalars.
- `search_gateway` tool schema intentionally exposes only `query` and `highlight_query`; runtime policy/domain/date constraints, focused domains, budgets, and recorders are injected via context and covered by tests.
- `SearchGateway` validates provider kwargs, focused-domain subsets, normalization, and dedupe, but does not independently reject provider-returned domain/date mismatches.
