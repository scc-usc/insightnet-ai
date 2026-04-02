"""
Agent 1 — Query Understanding.

understand_query(query) → QueryPlan via gpt-4.1-mini (json_object format).
"""

import json
import logging

from infra import openai_client
from models import QueryPlan

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You analyze user messages sent to an assistant that helps discover public health epidemic modeling tools.

Classify the user's intent and return a JSON object with these fields:
- intent: one of "find_tool" | "compare_tools" | "explain_tool" | "general_chat"
  Use "general_chat" for greetings, thank-yous, follow-up questions, off-topic messages, or anything that is NOT a request to find/compare/explain a specific tool.
- domain: the public health domain if relevant (e.g. "influenza", "COVID-19"), or "" if general chat
- keywords: list of search keywords, or [] if general chat
- preferred_collections: list from ["tool_profiles", "readme_chunks", "code_chunks"], or [] if general chat
- filters: optional dict of filters (e.g. {"difficulty": "low"}), or {} if general chat

Examples:
- "hello" → {"intent": "general_chat", "domain": "", "keywords": [], "preferred_collections": [], "filters": {}}
- "thanks that was helpful" → {"intent": "general_chat", ...}
- "what can you do?" → {"intent": "general_chat", ...}
- "find tools for COVID-19 modeling" → {"intent": "find_tool", "domain": "COVID-19", ...}
- "compare EpiModel and SEIR" → {"intent": "compare_tools", ...}"""


def understand_query(query: str) -> QueryPlan:
    try:
        raw = openai_client.chat(
            agent="agent1",
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
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
