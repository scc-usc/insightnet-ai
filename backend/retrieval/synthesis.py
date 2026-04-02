"""
Agent 4 — Recommendation + Synthesis.

Fetches full README for top-5, context-stuffs gpt-5.4, streams response.
run_query_pipeline(query, history) wraps Agent 1 → 2 → 3 → 4.
"""

import logging

from infra import openai_client
from infra.scraper import get_readme
from retrieval.query_understanding import understand_query
from retrieval.retrieval import embed_query, retrieve
from retrieval.reranker import rerank

logger = logging.getLogger(__name__)

# Status markers — frontend parses these to show progress
STATUS_UNDERSTANDING = "{{STATUS:Understanding your question...}}"
STATUS_SEARCHING = "{{STATUS:Searching tools...}}"
STATUS_RANKING = "{{STATUS:Ranking results...}}"
STATUS_WRITING = "{{STATUS:Writing response...}}"

SYSTEM_PROMPT = """You are InsightNet, a friendly assistant that helps researchers discover public health epidemic modeling tools and software.

When recommending tools, be conversational and helpful — not robotic. Write like you're talking to a colleague:
- Lead with your top recommendation and why it's a great fit
- Mention 2-4 other strong options briefly
- Include a short code snippet only if it genuinely helps the user get started
- Cite sources as [owner/repo] inline, linking to https://github.com/owner/repo
- If comparing tools, use a concise table

Keep responses focused and scannable. Use short paragraphs, not walls of text. Skip the tool if it's only marginally relevant — quality over quantity.

If the user's intent is "explain_tool", focus on explaining how that specific tool works with practical examples.

At the very end of your response, add a line break then exactly 3 follow-up suggestions the user might want to ask next, formatted as:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}

Make the suggestions specific and useful based on what you just recommended."""

CHAT_SYSTEM_PROMPT = """You are InsightNet, a friendly assistant that helps researchers discover public health epidemic modeling tools.

For general conversation:
- Be warm, concise, and helpful
- If the user greets you, greet them back and briefly mention what you can help with
- If they ask what you can do, explain that you help find, compare, and explain epidemic modeling tools and software
- If they thank you, acknowledge it naturally
- If their question is off-topic, gently steer them back to what you can help with
- Keep responses short — 1-3 sentences for casual messages

At the very end, add follow-up suggestions:
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}

Make the suggestions invite the user to try a tool search.

You are NOT a general-purpose chatbot. You specialize in epidemic modeling tools."""


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
    for i, result in enumerate(top_results[:5]):
        readme = get_readme(result.repo_name)
        context_parts.append(
            f"[Tool {i+1}: {result.repo_name}]\n"
            f"Relevance reason: {result.reason}\n\n"
            f"{readme[:3000]}"
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

    # Agent 3: Re-ranking (cosine + o3 judge)
    yield STATUS_RANKING
    top5 = rerank(query, embedding, top20)
    logger.info(f"Top 5: {[r.repo_name for r in top5]}")

    # Agent 4: Synthesis (streamed)
    yield STATUS_WRITING
    yield from synthesize(query, top5, plan.intent, history)
