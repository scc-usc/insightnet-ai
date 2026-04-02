"""
Agent 4 — Recommendation + Synthesis.

For tool queries: emits structured tool cards + brief conversational intro.
For general chat: streams a short response directly.
run_query_pipeline(query, history) wraps Agent 1 → 2 → 3 → 4.
"""

import json
import logging

from infra import openai_client
from infra.db import supabase
from infra.scraper import get_readme
from retrieval.query_understanding import understand_query
from retrieval.retrieval import embed_query, retrieve
from retrieval.reranker import cosine_rerank, rerank

logger = logging.getLogger(__name__)

# Status markers — frontend parses these to show progress
STATUS_UNDERSTANDING = "{{STATUS:Understanding your question...}}"
STATUS_SEARCHING = "{{STATUS:Searching tools...}}"
STATUS_RANKING = "{{STATUS:Ranking results...}}"
STATUS_WRITING = "{{STATUS:Writing response...}}"

TOOL_INTRO_PROMPT = """You are InsightNet. The user asked about epidemic modeling tools and you found results (shown as cards separately). Write ONLY a brief 1-2 sentence conversational intro — like texting a colleague.

Rules:
- 1-2 sentences MAX. Do NOT describe the tools — the cards handle that.
- Just say something like "Here's what I found" or "Great question — check these out"
- For compare intent, add one sentence about the key difference
- NEVER list tool names, bullet points, or details — cards show all that
- NEVER repeat the question back

End with:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}"""

CHAT_SYSTEM_PROMPT = """You are InsightNet, a friendly assistant for epidemic modeling tools.

- 1-2 sentences max for greetings, thanks, or off-topic
- Gently redirect off-topic to what you can help with
- You are NOT a general chatbot

End with:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}"""


def _build_history(history: list[dict], limit: int = 6) -> list[dict]:
    return history[-limit:] if history else []


def _get_tool_profile(repo_name: str) -> dict:
    """Fetch tool profile from Supabase."""
    try:
        result = supabase.table("tool_profiles").select("profile").eq("repo_name", repo_name).limit(1).execute()
        if result.data and result.data[0].get("profile"):
            return result.data[0]["profile"]
    except Exception as e:
        logger.error(f"Failed to fetch profile for {repo_name}: {e}")
    return {}


def _build_tool_cards(top_results: list) -> list[dict]:
    """Build structured tool card data from ranked results + Supabase profiles."""
    cards = []
    for i, result in enumerate(top_results):
        profile = _get_tool_profile(result.repo_name)
        readme = get_readme(result.repo_name)

        cards.append({
            "rank": i + 1,
            "repo_name": result.repo_name,
            "tool_name": profile.get("tool_name", result.repo_name.split("/")[-1]),
            "one_line": profile.get("one_line", result.chunk_text[:120]),
            "reason": result.reason or "",
            "tags": profile.get("tags", [])[:4],
            "difficulty": profile.get("difficulty", ""),
            "use_cases": profile.get("use_cases", [])[:3],
            "github_url": f"https://github.com/{result.repo_name}",
            "readme_preview": readme[:300] if readme else "",
            "score": round(result.score, 3),
        })
    return cards


def _chat_response(query: str, history: list[dict]):
    """Handle general chat without the retrieval pipeline."""
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": query})

    return openai_client.chat(
        agent="agent4-chat",
        model="gpt-4.1-mini",
        messages=messages,
        stream=True,
    )


def _tool_intro(query: str, intent: str, tool_names: list[str], history: list[dict]):
    """Generate a brief 1-2 sentence intro for tool results."""
    messages = [{"role": "system", "content": TOOL_INTRO_PROMPT}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": f"Query: {query}\nIntent: {intent}\nTools found: {', '.join(tool_names)}"})

    return openai_client.chat(
        agent="agent4-intro",
        model="gpt-4.1-mini",
        messages=messages,
        stream=True,
    )


def run_query_pipeline(query: str, history: list[dict] | None = None):
    """Full pipeline: Agent 1 → 2 → 3 → 4. Yields status markers, tool cards, then streams intro."""
    history = history or []
    logger.info(f"Query pipeline start: {query!r}")

    # Agent 1: Query Understanding
    yield STATUS_UNDERSTANDING
    plan = understand_query(query)
    logger.info(f"Intent={plan.intent}, collections={plan.preferred_collections}")

    # General chat — skip retrieval entirely
    if plan.intent == "general_chat":
        logger.info("Routing to general chat (no retrieval)")
        yield from _chat_response(query, history)
        return

    # Agent 2: Retrieval + RRF
    yield STATUS_SEARCHING
    embedding = embed_query(query)
    top20 = retrieve(plan, embedding)
    logger.info(f"Retrieved {len(top20)} candidates")

    # Agent 3: Re-ranking
    yield STATUS_RANKING
    if plan.intent == "find_tool":
        top3 = cosine_rerank(embedding, top20, top_n=3)
    else:
        top3 = rerank(query, embedding, top20)[:3]
    logger.info(f"Top results: {[r.repo_name for r in top3]}")

    # Build and emit tool cards (instant, no LLM needed)
    yield STATUS_WRITING
    cards = _build_tool_cards(top3)
    yield "{{TOOLS:" + json.dumps(cards) + "}}"

    # Stream brief conversational intro
    tool_names = [c["tool_name"] for c in cards]
    yield from _tool_intro(query, plan.intent, tool_names, history)
