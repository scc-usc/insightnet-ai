"""
Agent 4 — Recommendation + Synthesis.

Fetches full README for top results, context-stuffs gpt-5.4, streams response.
run_query_pipeline(query, history) wraps Agent 1 → 2 → 3 → 4.
"""

import logging

from infra import openai_client
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

SYSTEM_PROMPT = """You are InsightNet, a helpful assistant for finding epidemic modeling tools. Talk like a knowledgeable colleague, not a search engine.

CRITICAL RULES:
- Keep total response under 150 words
- Lead with your #1 pick in 1-2 natural sentences
- Mention 1-2 alternatives in one line each if relevant
- NO numbered lists, NO "BEST PICK" headers, NO bullet-point dumps
- Only show code if the user asked for it
- Cite tools as [source: owner/repo]
- For comparisons: one small table, no extra text
- Never repeat the question back

Write like a text message to a smart colleague — brief, direct, useful.

End with:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}"""

CHAT_SYSTEM_PROMPT = """You are InsightNet, a friendly assistant for epidemic modeling tools.

- 1-2 sentences max for greetings, thanks, or off-topic
- Gently redirect off-topic to what you can help with
- You are NOT a general chatbot

End with:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}"""


def _build_history(history: list[dict], limit: int = 6) -> list[dict]:
    """Take the last N messages from history for context."""
    return history[-limit:] if history else []


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


def synthesize(query: str, top_results: list, intent: str, history: list[dict]):
    """Context-stuff gpt-5.4 with full READMEs and stream the response."""
    context_parts = []
    for i, result in enumerate(top_results[:3]):
        readme = get_readme(result.repo_name)
        context_parts.append(
            f"[Tool {i+1}: {result.repo_name}]\n"
            f"Relevance: {result.reason}\n\n"
            f"{readme[:2000]}"
        )

    context = "\n\n---\n\n".join(context_parts)
    user_msg = f"Query: {query}\nIntent: {intent}\n\n{context}"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": user_msg})

    return openai_client.chat(
        agent="agent4",
        model="gpt-5.4",
        messages=messages,
        stream=True,
    )


def run_query_pipeline(query: str, history: list[dict] | None = None):
    """Full pipeline: Agent 1 → 2 → 3 → 4. Yields status markers then streams response."""
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
        # Simple find → cosine only (skip expensive o3 judge, ~5x faster)
        top3 = cosine_rerank(embedding, top20, top_n=3)
        logger.info(f"Cosine top 3: {[r.repo_name for r in top3]}")
    else:
        # Compare/explain → full rerank with o3 judge for quality
        top3 = rerank(query, embedding, top20)[:3]
        logger.info(f"Full rerank top 3: {[r.repo_name for r in top3]}")

    # Agent 4: Synthesis (streamed)
    yield STATUS_WRITING
    yield from synthesize(query, top3, plan.intent, history)
