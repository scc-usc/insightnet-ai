"""
Agent 1 — Query Understanding.

understand_query(query, history) → QueryPlan via gpt-4.1-mini (json_object format).
Uses conversation history to resolve ambiguous references like "tools" or "it".
"""

import json
import logging

from infra import openai_client
from models import QueryPlan

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You analyze user messages for InsightNet AI, an assistant for epidemic modeling tools.

You receive the user's message AND conversation history. The history may include [Previously shown tools: ...] annotations showing what tools were already presented to the user.

CLASSIFICATION RULES (apply in this priority order):

1. "discuss_results" — The user references previously shown tools and wants help choosing, understanding differences, or discussing them ("which is best?", "help me choose", "what's the difference between these?", "pros and cons?", "which one for my project?"). REQUIRES tools to have been shown in history.

2. "followup_tool" — The user asks a specific question about a tool that was shown or named ("does Epydemix support real-time data?", "can I use the first one for vaccination?", "how do I install that?"). REQUIRES a specific tool to be identifiable.

3. "explain_tool" — The user names a specific tool and wants to learn about it ("tell me about Epydemix", "what does the second one do?", "tell me more about the first one").

4. "compare_tools" — The user explicitly wants a side-by-side comparison of named or shown tools ("compare Epydemix and multigroup.vaccine", "compare these two").

5. "find_tool" — The user wants to discover NEW tools ("find tools for COVID", "what tools exist for SIR modeling?", "show me something for influenza", "these don't fit, show me others").

6. "general_chat" — Pure greetings ("hi", "hello"), thanks ("thanks!", "got it"), or completely off-topic ("what's the weather?").

CRITICAL: If tools were previously shown in history and the user's question could relate to them, prefer "discuss_results" or "followup_tool" over "find_tool". Only use "find_tool" when the user clearly wants NEW tools they haven't seen yet.

Return a JSON object:
- intent: one of the 6 intents above
- domain: the public health domain from the message or context (e.g. "COVID-19"), or ""
- keywords: search keywords inferred from BOTH the current message AND history context
- preferred_collections: list from ["tool_profiles", "readme_chunks", "code_chunks"], or []
- filters: optional dict, or {}
- referenced_tools: list of repo_names (e.g. ["owner/repo"]) the user is referring to, extracted from [Previously shown tools] annotations, or []

Examples (with tools previously shown: 1. Epydemix, 2. multigroup.vaccine, 3. SEIR-model):
- "which one is best for COVID?" → discuss_results, referenced_tools from history
- "does Epydemix support real-time data?" → followup_tool, referenced_tools: ["cmu-delphi/Epydemix"]
- "tell me more about the second one" → explain_tool, referenced_tools: [second tool from history]
- "compare the first two" → compare_tools, referenced_tools: [first two from history]
- "find me something for influenza" → find_tool (new domain)
- "these don't fit, show me others" → find_tool (explicit rejection)
- "thanks!" → general_chat

Examples (no tools previously shown):
- "what tools are good for SIR?" → find_tool
- "hello" → general_chat
- "I have COVID data, how do I use it?" → find_tool"""


def understand_query(query: str, history: list[dict] | None = None, model: str | None = None) -> QueryPlan:
    history = history or []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include last 4 conversation turns for context
    for msg in history[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": query})

    # Query understanding is an internal classification task — always use the
    # default model (which reliably supports json_mode), not the user's pick.
    try:
        raw = openai_client.chat_router(
            agent="agent1",
            messages=messages,
            json_mode=True,
        )
        data = json.loads(raw)
        return QueryPlan(
            intent=data.get("intent", "find_tool"),
            domain=data.get("domain", ""),
            keywords=data.get("keywords", []),
            preferred_collections=data.get("preferred_collections", ["tool_profiles", "readme_chunks", "code_chunks"]),
            filters=data.get("filters", {}),
            referenced_tools=data.get("referenced_tools", []),
        )
    except Exception as e:
        logger.warning(f"Query understanding failed: {e}")
        # Simple heuristic fallback for common patterns
        q = query.strip().lower()
        if q in ("hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "goodbye"):
            return QueryPlan(intent="general_chat", keywords=[])
        return QueryPlan(intent="find_tool", keywords=query.split()[:5])
