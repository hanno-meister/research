RESEARCH_BRIEF_PROMPT = """You are helping transform a user's research intent into a precise research brief.
User research intent:
{research_intent}
Write a focused research brief that:
- preserves the user's original goal
- clarifies what should be investigated
- lists important dimensions to cover
- avoids inventing unsupported constraints
- is specific enough for a research agent to execute
Return only the research brief.
"""


RESEARCH_PLAN_PROMPT = """You are planning bounded research tasks for worker research agents.

User research intent:
{research_intent}

Research brief:
{research_brief}

Runtime constraints supplied by the application, not by you:
{runtime_constraints}

Create a compact set of non-overlapping research tasks that worker agents can execute independently.

Rules:
- Preserve the research brief's goal.
- Split only where the brief benefits from distinct lines of inquiry.
- Prefer 2-4 tasks for normal research, 1 task for narrow fact-finding, and at most 5 tasks for broad research.
- Give each task clear boundaries so workers do not duplicate each other.
- focused_domains are only optional focus hints. They must not broaden or override runtime constraints.
- If allowed domains are provided, only include focused_domains from that allowed set.
- Do not invent hard date/domain constraints.
- expected_output should describe the compact structured findings the worker should return.
"""
