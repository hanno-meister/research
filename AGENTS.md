# AGENTS.md

## Project shape

- Python 3.11 project managed by `uv`; update `uv.lock` with `pyproject.toml` dependency changes.
- The LangGraph app is `src/vanguard/graph.py`; root `main.py` is only a hello-world placeholder.
- `graph.py` exposes `builder` and currently wires `write_research_brief -> conduct_research -> final_report_generation`.
- State/config/prompt contracts live in `src/vanguard/state.py`, `src/vanguard/langgraph_configuration.py`, and `src/vanguard/prompts.py`.
- `src/vanguard/search_gateway.py` is standalone provider plumbing for Exa/Tavily; tests inject fake clients and should not call external search APIs.

## Commands

- Install/sync dependencies: `uv sync`.
- Run all tests: `uv run pytest`.
- Run one test file: `uv run pytest tests/test_search_gateway.py`.
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
- `AgentState.research_findings` uses `Annotated[list[str], operator.add]`; node returns should append lists, not replace with a scalar.
