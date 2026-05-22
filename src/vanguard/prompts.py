RESEARCH_BRIEF_PROMPT = """You are helping transform a user's research intent into a precise research brief.

User research intent:
{research_intent}

Selected internal research Lance context, if any:
{selected_lance}

Date window, if any:
{date_window}

Write a focused research brief that:
- preserves the user's original goal exactly as stated, separating what the user explicitly asked for from reasonable inferred research dimensions
- uses the selected Lance context to clarify relevance, terminology, and scouting priorities when provided
- when the Lance context names specific systems, models, or platforms, treats those as required coverage targets — use "must investigate" or "required coverage" rather than "such as" or "including but not limited to"
- for each required coverage target, specifies what kind of primary source evidence is expected: API or developer documentation for products with a programmatic surface, official product or architecture documentation for platforms and infrastructure systems, comparative capability evidence or third-party evaluation for categories where direct primary sources are unlikely to consolidate the relevant claims, and peer-reviewed or preprint research for academic or benchmark systems
- if a date window is provided, states it explicitly as a research constraint and instructs that sources outside the window should be flagged rather than silently used
- distinguishes between required coverage targets and required coverage categories: a target is a named system that must be investigated directly; a category is a broader area where the brief should specify what questions remain unanswerable if coverage of that category is missing
- does not add research dimensions that are not supported by the user's intent or Lance context — if a dimension is inferred rather than explicit, mark it as inferred
- does not replace or narrow the user's request beyond what the user or Lance context supports
- notes uncertainty or missing scope instead of filling gaps with assumptions
- is specific enough for a research agent to execute

Return only the research brief.
"""


RESEARCH_PLAN_PROMPT = """You are planning bounded research tasks for worker research agents.

User research intent:
{research_intent}

Selected internal research Lance context, if any:
{selected_lance}

Research brief:
{research_brief}

Runtime constraints supplied by the application, not by you:
{runtime_constraints}

Create a useful set of non-overlapping research tasks that worker agents can execute independently.

Rules:

TASK DESIGN
- Preserve the research brief's goal.
- Use enough tasks to cover clearly independent systems, subtopics, or evidence needs without duplicating work.
- Prefer fewer tasks when one worker can cover the brief well, but split when separate workers would improve coverage or source discovery.
- Never return more than {max_research_tasks} tasks.
- Give each task clear boundaries so workers do not duplicate each other.
- Use the selected Lance context to make tasks relevant for that technical audience.

TARGET TERMS
- Populate target_terms with named systems, benchmarks, labs, datasets, methods, and capability terms the worker should explicitly check.
- Include target_terms from the user's request and selected Lance description when present, plus likely adjacent terms that improve search recall.
- Treat target_terms only as search targets and coverage prompts, not as established facts.
- When the brief names specific systems, models, or platforms as required coverage, ensure each named system appears in target_terms of at least two tasks with different focused_domains, so coverage does not depend on a single domain set returning useful results.

SOURCE AND DOMAIN GUIDANCE
- Prefer tasks that can be answered from primary, official, regulatory, academic, or established expert sources when available.
- Include source-quality expectations in expected_output when the question depends on recency, claims, forecasts, prices, market reaction, or disputed facts.
- focused_domains must be a subset of the allowed_domains provided in runtime_constraints. If runtime constraints would prevent useful coverage of a topic, scope the task to what is supportable and instruct the worker to surface the limitation in source_diversity_notes rather than attempting unsupported domains.
- When constructing focused_domains for each task, consider what domain types best match the evidence needed. Vendor and industry coverage typically requires non-arxiv domains. Technical methods typically require arxiv plus official research blogs. Avoid defaulting every task to the same domain set.

DATE WINDOW
- If the research brief includes a date window, propagate it explicitly into each task's boundaries and expected_output. Instruct workers to flag sources outside the window rather than silently use them, and to note when coverage is limited by the date constraint.

TASK DEPENDENCIES
- Use depends_on when a task synthesizes, compares, or recommends based on evidence produced by other tasks; keep evidence-gathering tasks independent when possible.
- If a final recommendation/synthesis task depends on earlier inventory, capability, or benchmark tasks, set depends_on to those task IDs instead of making it run in the first fan-out.

- Do not invent hard date/domain constraints beyond what the research brief and runtime constraints supply.
- expected_output should describe the compact structured findings the worker should return.
"""
