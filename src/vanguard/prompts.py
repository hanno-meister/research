RESEARCH_BRIEF_PROMPT = """You are helping transform a user's research intent into a precise research brief.
User research intent:
{research_intent}
Write a focused research brief that:
- preserves the user's original goal
- clarifies what should be investigated
- lists important dimensions to cover
- avoids inventing unsupported constraints
- separates what the user explicitly asked for from reasonable research dimensions
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
- Preserve the research brief's goal.
- Use enough tasks to cover clearly independent systems, subtopics, or evidence needs without duplicating work.
- Prefer fewer tasks when one worker can cover the brief well, but split when separate workers would improve coverage or source discovery.
- Never return more than {max_research_tasks} tasks.
- Give each task clear boundaries so workers do not duplicate each other.
- Use the selected Lance context to make tasks relevant for that technical audience.
- Populate target_terms with named systems, benchmarks, labs, datasets, methods, and capability terms the worker should explicitly check.
- Include target_terms from the user's request and selected Lance description when present, plus likely adjacent terms that improve search recall.
- Treat target_terms only as search targets and coverage prompts, not as established facts.
- Prefer tasks that can be answered from primary, official, regulatory, academic, or established expert sources when available.
- Include source-quality expectations in expected_output when the question depends on recency, claims, forecasts, prices, market reaction, or disputed facts.
- focused_domains are only optional focus hints. They must not broaden or override runtime constraints.
- If allowed domains are provided, only include focused_domains from that allowed set.
- Do not invent hard date/domain constraints.
- If runtime constraints are likely to limit coverage, keep tasks scoped to what can be supported and have workers surface limitations; do not create tasks that require unavailable domains.
- expected_output should describe the compact structured findings the worker should return.
"""
