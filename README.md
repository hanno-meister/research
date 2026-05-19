# Vanguard v3

Vanguard v3 is a Python 3.11 research-agent service built with LangGraph, LangChain, DeepAgents, and FastAPI. It turns a research intent into a structured research brief, plans focused research tasks, gathers evidence through Exa and Tavily, reviews the evidence, and returns a final Markdown report.

## What it does

- Builds a LangGraph workflow for deep research.
- Generates a normalized research brief from a user request.
- Plans bounded research tasks with optional domain and date constraints.
- Searches external providers through a policy-aware gateway.
- Stores research evidence under virtual `/evidence/` paths backed by local `.vanguard/` storage.
- Reviews evidence before generating the final report.
- Exposes the workflow through a FastAPI `POST /research` endpoint.

## Project layout

```text
.
├── src/vanguard/
│   ├── api.py                     # FastAPI app and /research endpoint
│   ├── graph.py                   # LangGraph builder and workflow wiring
│   ├── langgraph_configuration.py # Runtime configuration model
│   ├── state.py                   # Graph input/state contracts
│   ├── prompts.py                 # Prompt contracts
│   └── research/
│       └── search_gateway.py      # Exa/Tavily provider gateway
├── tests/                         # Unit and API tests
├── pyproject.toml                 # Project metadata and Vanguard model config
└── uv.lock                        # Locked dependency graph
```

The graph runs this sequence:

```text
write_research_brief -> plan_research -> conduct_research -> review_research -> final_report_generation
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Azure OpenAI-compatible API access
- Optional search provider keys for live research:
  - Exa API key
  - Tavily API key

## Setup

Install dependencies:

```bash
uv sync
```

Create a local `.env` file. It is ignored by git.

```env
AZURE_OPENAI_API_KEY=your_azure_openai_key
EXA_API_KEY=your_exa_key
TAVILY_API_KEY=your_tavily_key
```

Model names and the OpenAI-compatible base URL are configured in `pyproject.toml` under `[tool.vanguard]`:

```toml
[tool.vanguard]
small_model = "gpt-5.4-mini"
large_model = "gpt-5.5"
openai_base_url = "https://cop-deep-research.services.ai.azure.com/openai/v1"
```

## Run the API

FastAPI is installed with the `standard` extra, so you can run the app with:

```bash
uv run fastapi dev src/vanguard/api.py
```

Then call the research endpoint:

```bash
curl -X POST http://127.0.0.1:8000/research \
  -H 'Content-Type: application/json' \
  -d '{
    "human_message": "Research LangGraph patterns for deep research agents",
    "allowed_domains": ["langchain.com", "github.com"],
    "verbose": false
  }'
```

Response shape:

```json
{
  "final_report": "...",
  "status": "sufficient",
  "research_brief": "...",
  "source_count": 8,
  "review_rounds": 1
}
```

Set `verbose` to `true` to include the full graph state in the `debug` field.

## Run the graph directly

`src/vanguard/graph.py` includes a small demo entrypoint:

```bash
uv run python -m src.vanguard.graph
```

You can smoke-test graph compilation without making an API call:

```bash
AZURE_OPENAI_API_KEY=dummy uv run python -c "from src.vanguard.graph import builder; builder.compile(); print('graph compiles')"
```

## Testing

Run the full test suite:

```bash
uv run pytest
```

Run targeted tests:

```bash
uv run pytest tests/test_api.py
uv run pytest tests/test_search_gateway.py
uv run pytest tests/test_graph.py::test_search_gateway_tool_schema_hides_runtime_policy
```

Tests inject fake search clients and must not call external search APIs.

## Configuration notes

- `.env` is loaded with `python-dotenv`.
- Importing graph configuration requires `AZURE_OPENAI_API_KEY`; use a dummy value only for compile/import smoke tests.
- `EXA_API_KEY` and `TAVILY_API_KEY` are required only for default live provider adapters.
- API responses are compact by default. Use request `verbose: true` for full graph-state debugging.
- Evidence artifacts are exposed to the workflow as `/evidence/...` paths and backed by local `.vanguard/` storage.

## Development notes

- Keep dependency changes in sync between `pyproject.toml` and `uv.lock`.
- Runtime model configuration belongs in `[tool.vanguard]`, not hard-coded in graph nodes.
- The search gateway tool schema intentionally exposes only `query` and `highlight_query`; policy constraints are injected at runtime.
