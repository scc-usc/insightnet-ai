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

SYSTEM_PROMPT = """You analyze user messages sent to InsightNet, an assistant that finds public health epidemic modeling tools.

You receive the user's message AND recent conversation history. Use the history to resolve references like "tools", "it", "those", "more", etc.

IMPORTANT: Default to "find_tool" when uncertain. Only use "general_chat" for pure greetings ("hi", "hello", "thanks") or completely off-topic messages (e.g., "what's the weather?").

If the user mentions tools, recommendations, data, models, frameworks, libraries, code, or anything tool-related — even vaguely — classify as "find_tool".

Return a JSON object:
- intent: "find_tool" | "compare_tools" | "explain_tool" | "general_chat"
- domain: the public health domain from the message OR conversation context (e.g. "COVID-19"), or ""
- keywords: search keywords inferred from BOTH the current message AND history context
- preferred_collections: list from ["tool_profiles", "readme_chunks", "code_chunks"], or []
- filters: optional dict, or {}

Examples:
- "hello" → general_chat
- "thanks!" → general_chat
- "what tools are good?" → find_tool (even without specifying a domain — use history for context)
- "can you recommend toolkits?" → find_tool
- "I have COVID data, how do I use it?" → find_tool (user is implicitly asking for tools)
- "tell me more about the first one" → explain_tool
- "compare those" → compare_tools"""


def understand_query(query: str, history: list[dict] | None = None) -> QueryPlan:
    history = history or []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include last 4 conversation turns for context
    for msg in history[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": query})

    try:
        raw = openai_client.chat(
            agent="agent1",
            model="gpt-4.1-mini",
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
        )
    except Exception as e:
        logger.error(f"Query understanding failed: {e}")
        return QueryPlan(intent="find_tool", keywords=query.split()[:5])
