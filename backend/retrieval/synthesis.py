"""
Agent 4 — Recommendation + Synthesis.

Fetches full README for top-5, context-stuffs gpt-5.4, streams response.
run_query_pipeline(query) wraps Agent 1 → 2 → 3 → 4.
"""

import logging

from infra import openai_client
from infra.scraper import get_readme
from retrieval.query_understanding import understand_query
from retrieval.retrieval import embed_query, retrieve
from retrieval.reranker import rerank

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are InsightNet, a friendly assistant that helps researchers discover public health epidemic modeling tools and software.

When recommending tools, be conversational and helpful — not robotic. Write like you're talking to a colleague:
- Lead with your top recommendation and why it's a great fit
- Mention 2-4 other strong options briefly
- Include a short code snippet only if it genuinely helps the user get started
- Cite sources as [owner/repo] inline
- If comparing tools, use a concise table

Keep responses focused and scannable. Use short paragraphs, not walls of text. Skip the tool if it's only marginally relevant — quality over quantity.

If the user's intent is "explain_tool", focus on explaining how that specific tool works with practical examples."""

CHAT_SYSTEM_PROMPT = """You are InsightNet, a friendly assistant that helps researchers discover public health epidemic modeling tools.

For general conversation:
- Be warm, concise, and helpful
- If the user greets you, greet them back and briefly mention what you can help with
- If they ask what you can do, explain that you help find, compare, and explain epidemic modeling tools and software
- If they thank you, acknowledge it naturally
- If their question is off-topic, gently steer them back to what you can help with
- Keep responses short — 1-3 sentences for casual messages

You are NOT a general-purpose chatbot. You specialize in epidemic modeling tools."""


def _chat_response(query: str):
    """Handle general chat without the retrieval pipeline."""
    return openai_client.chat(
        agent="agent4-chat",
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        stream=True,
    )


def synthesize(query: str, top_results: list, intent: str):
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

    return openai_client.chat(
        agent="agent4",
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        stream=True,
    )


def run_query_pipeline(query: str):
    """Full pipeline: Agent 1 → 2 → 3 → 4. Returns a streaming response."""
    logger.info(f"Query pipeline start: {query!r}")

    # Agent 1: Query Understanding
    plan = understand_query(query)
    logger.info(f"Intent={plan.intent}, collections={plan.preferred_collections}")

    # General chat — skip retrieval entirely
    if plan.intent == "general_chat":
        logger.info("Routing to general chat (no retrieval)")
        return _chat_response(query)

    # Agent 2: Retrieval + RRF
    embedding = embed_query(query)
    top20 = retrieve(plan, embedding)
    logger.info(f"Retrieved {len(top20)} candidates")

    # Agent 3: Re-ranking (cosine + o3 judge)
    top5 = rerank(query, embedding, top20)
    logger.info(f"Top 5: {[r.repo_name for r in top5]}")

    # Agent 4: Synthesis (streamed)
    return synthesize(query, top5, plan.intent)
