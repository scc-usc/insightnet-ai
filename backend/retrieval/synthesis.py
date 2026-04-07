"""
Agent 4 — Recommendation + Synthesis.

For tool queries: emits structured tool cards + brief conversational intro.
For explain queries: gives a detailed explanation without re-searching.
For discuss/followup queries: answers using previously shown tool context.
For general chat: streams a conversational response.
run_query_pipeline(query, history) wraps Agent 1 → 2 → 3 → 4.
"""

import json
import logging
import re

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

# ── Prompts ─────────────────────────────────────────────────────────

FORMATTING_INSTRUCTIONS = """
Choose the response format that best helps the user understand and act on the answer:
- Use **bold** for key terms or tool names the user should notice
- Use bullet points or numbered lists when comparing multiple items or listing steps
- Use tables when comparing features across tools side-by-side
- Use code blocks with backticks for commands, install instructions, or code
- Use headers (###) to organize longer responses into scannable sections
- Use short paragraphs for conversational explanations
- Keep it concise — don't pad with filler. Every sentence should add value.
Adapt naturally: a simple question gets a simple answer, a complex question gets structure."""

FOLLOWUPS_INSTRUCTION = """
End every response with exactly this format (three suggestions separated by ||):
{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}
Make the suggestions specific and relevant to what was just discussed — never generic."""

TOOL_INTRO_PROMPT = f"""You are InsightNet, an expert assistant for epidemic modeling tools. You found tools matching the user's query (shown as cards separately). Write a brief intro that connects the results to the user's specific need.

Rules:
- Keep it short — 2-3 sentences. The cards show the details.
- Reference the user's specific need, don't say generic "here's what I found"
- If comparing: highlight the key difference
- NEVER list tool names, bullet points, or details — the cards handle that
- NEVER repeat the question back
{FOLLOWUPS_INSTRUCTION}"""

CHAT_SYSTEM_PROMPT = f"""You are InsightNet, an expert assistant for epidemic modeling tools and methods.

You help with:
- Epidemic modeling concepts (SIR, SEIR, agent-based, compartmental, network models, etc.)
- Choosing the right approach for a user's research
- Domain questions about epidemiology, public health modeling, and data analysis
- Methodology guidance, not just tool selection

Be conversational and knowledgeable — like a helpful colleague in the lab. When a question could benefit from a tool search, suggest it naturally.

If truly off-topic (weather, cooking, etc.), briefly redirect to what you can help with.
{FORMATTING_INSTRUCTIONS}
{FOLLOWUPS_INSTRUCTION}"""

EXPLAIN_PROMPT = f"""You are InsightNet. The user wants to know more about an epidemic modeling tool.

Use the tool's profile and README data provided to give a thorough, helpful explanation. Cover what the user needs to understand — what it does, who it's for, how to get started, key features, limitations.

Cite the source as [source: owner/repo].

If the user has already seen an explanation and is asking a follow-up question, answer their specific question directly — don't repeat information they already have.
{FORMATTING_INSTRUCTIONS}
{FOLLOWUPS_INSTRUCTION}"""

_DISCUSS_TEMPLATE = """You are InsightNet. The user is asking about tools you previously showed them.

Use the tool profiles below to give a thoughtful, specific answer. Reference tools by name. Give clear recommendations with reasoning based on what the user needs. If you don't have enough info about their use case, ask a clarifying question.

Previously shown tool profiles:
{tool_context}
""" + FORMATTING_INSTRUCTIONS + """
End every response with exactly this format (three suggestions separated by ||):
{{{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}}}
Make the suggestions specific and relevant to what was just discussed — never generic."""

_FOLLOWUP_TEMPLATE = """You are InsightNet. The user is asking a specific question about an epidemic modeling tool.

Use the tool's profile and README below to answer their question directly with specific, accurate information from the data. Don't give generic overviews unless that's what was asked.

Tool context:
{tool_context}
""" + FORMATTING_INSTRUCTIONS + """
End every response with exactly this format (three suggestions separated by ||):
{{{{FOLLOWUPS:suggestion one||suggestion two||suggestion three}}}}
Make the suggestions specific and relevant to what was just discussed — never generic."""


# ── Helpers ─────────────────────────────────────────────────────────

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


def _extract_shown_tools_from_history(history: list[dict]) -> list[str]:
    """Extract repo_names from [Previously shown tools: ...] annotations in history."""
    repo_names = []
    for msg in reversed(history):
        match = re.search(r'\[Previously shown tools:\n(.+?)\]', msg.get("content", ""), re.DOTALL)
        if match:
            for line in match.group(1).strip().split("\n"):
                # Format: "1. ToolName (owner/repo) — description"
                repo_match = re.search(r'\(([^)]+/[^)]+)\)', line)
                if repo_match:
                    repo_names.append(repo_match.group(1))
            if repo_names:
                break  # Use the most recent set of shown tools
    return repo_names


def _extract_repo_from_context(query: str, history: list[dict], referenced_tools: list[str] | None = None) -> str | None:
    """Try to find a repo name from referenced_tools, history annotations, or text matching."""
    # First: use referenced_tools from query understanding
    if referenced_tools:
        return referenced_tools[0]

    # Second: check for ordinal references against shown tools
    shown = _extract_shown_tools_from_history(history)
    query_lower = query.lower()
    ordinals = {"first": 0, "second": 1, "third": 2, "1st": 0, "2nd": 1, "3rd": 2}
    for word, idx in ordinals.items():
        if word in query_lower and idx < len(shown):
            return shown[idx]

    # Third: text match against all tool names
    all_text = query_lower
    for msg in reversed(history[-6:]):
        all_text += " " + msg.get("content", "").lower()

    try:
        result = supabase.table("tool_profiles").select("repo_name,profile").execute()
        if result.data:
            for row in result.data:
                profile = row.get("profile", {})
                tool_name = profile.get("tool_name", "").lower()
                repo = row["repo_name"].lower()
                repo_short = repo.split("/")[-1].lower()

                if tool_name and tool_name in all_text:
                    return row["repo_name"]
                if repo_short in all_text:
                    return row["repo_name"]
    except Exception:
        pass
    return None


def _build_tool_context(repo_names: list[str]) -> str:
    """Build a context string with profiles and README snippets for given repos."""
    parts = []
    for repo_name in repo_names:
        profile = _get_tool_profile(repo_name)
        readme = get_readme(repo_name)
        section = f"Tool: {repo_name}\n"
        if profile:
            section += f"Profile: {json.dumps(profile)}\n"
        if readme:
            section += f"README (first 2000 chars):\n{readme[:2000]}\n"
        parts.append(section)
    return "\n---\n".join(parts)


# ── Response handlers ───────────────────────────────────────────────

def _chat_response(query: str, history: list[dict]):
    """Handle general chat with conversational domain knowledge."""
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": query})

    return openai_client.chat(
        agent="agent4-chat",
        model="gpt-4.1-mini",
        messages=messages,
        stream=True,
    )


def _explain_tool(query: str, history: list[dict], referenced_tools: list[str] | None = None):
    """Explain a specific tool using its README and profile, without re-searching."""
    repo_name = _extract_repo_from_context(query, history, referenced_tools)
    if not repo_name:
        return None

    context = _build_tool_context([repo_name])

    messages = [{"role": "system", "content": EXPLAIN_PROMPT}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": f"{query}\n\n{context}"})

    return openai_client.chat(
        agent="agent4-explain",
        model="gpt-4.1-mini",
        messages=messages,
        stream=True,
    )


def _discuss_results(query: str, history: list[dict], referenced_tools: list[str] | None = None):
    """Answer questions about previously shown tools using conversation context."""
    # Get tools from referenced_tools or history
    repo_names = referenced_tools if referenced_tools else _extract_shown_tools_from_history(history)

    if not repo_names:
        return None

    tool_context = _build_tool_context(repo_names)
    system = _DISCUSS_TEMPLATE.format(tool_context=tool_context)

    messages = [{"role": "system", "content": system}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": query})

    return openai_client.chat(
        agent="agent4-discuss",
        model="gpt-4.1-mini",
        messages=messages,
        stream=True,
    )


def _followup_tool(query: str, history: list[dict], referenced_tools: list[str] | None = None):
    """Answer a specific question about a tool using its full context."""
    repo_name = _extract_repo_from_context(query, history, referenced_tools)
    if not repo_name:
        return None

    tool_context = _build_tool_context([repo_name])
    system = _FOLLOWUP_TEMPLATE.format(tool_context=tool_context)

    messages = [{"role": "system", "content": system}]
    messages.extend(_build_history(history))
    messages.append({"role": "user", "content": query})

    return openai_client.chat(
        agent="agent4-followup",
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


# ── Main pipeline ──────────────────────────────────────────────────

def run_query_pipeline(query: str, history: list[dict] | None = None):
    """Full pipeline: Agent 1 → route by intent → respond. Yields status markers, tool cards, then streams."""
    history = history or []
    logger.info(f"Query pipeline start: {query!r}")

    # Agent 1: Query Understanding (with conversation history for context)
    yield STATUS_UNDERSTANDING
    plan = understand_query(query, history)
    logger.info(f"Intent={plan.intent}, keywords={plan.keywords}, referenced_tools={plan.referenced_tools}")

    # ── Route by intent ─────────────────────────────────────────────

    # General chat — skip retrieval entirely
    if plan.intent == "general_chat":
        logger.info("Routing to general chat (no retrieval)")
        yield from _chat_response(query, history)
        return

    # Discuss results — answer about previously shown tools
    if plan.intent == "discuss_results":
        logger.info("Routing to discuss results (no new search)")
        yield STATUS_WRITING
        stream = _discuss_results(query, history, plan.referenced_tools)
        if stream is not None:
            yield from stream
            return
        logger.info("Could not find shown tools, falling back to search")

    # Follow-up tool — answer specific question about a tool
    if plan.intent == "followup_tool":
        logger.info("Routing to followup tool")
        yield STATUS_WRITING
        stream = _followup_tool(query, history, plan.referenced_tools)
        if stream is not None:
            yield from stream
            return
        logger.info("Could not identify tool, falling back to search")

    # Explain tool — try to answer from existing data without re-searching
    if plan.intent == "explain_tool":
        logger.info("Routing to explain tool")
        yield STATUS_WRITING
        explain_stream = _explain_tool(query, history, plan.referenced_tools)
        if explain_stream is not None:
            yield from explain_stream
            return
        logger.info("Could not identify tool, falling back to search")

    # ── Search pipeline (find_tool / compare_tools / fallbacks) ─────

    # Agent 2: Retrieval + RRF
    yield STATUS_SEARCHING
    embedding = embed_query(query)
    top20 = retrieve(plan, embedding)
    logger.info(f"Retrieved {len(top20)} candidates")

    # Deduplicate: exclude tools already shown in this conversation
    shown_repos = _extract_shown_tools_from_history(history)
    if shown_repos and plan.intent == "find_tool":
        # Only exclude if user is looking for NEW tools (not compare)
        top20 = [r for r in top20 if r.repo_name not in shown_repos] or top20
        logger.info(f"After dedup: {len(top20)} candidates (excluded {shown_repos})")

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
