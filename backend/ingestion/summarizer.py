"""
Agent 0 -- Tool Summarizer.

summarize_repo():  gpt-4.1-mini -> JSON tool profile (returned to caller, no DB writes)
chunk_and_embed(): used by updater for re-ingestion (writes to Supabase + ChromaDB)
"""

import json
import logging

from infra import openai_client
from infra.firestore_db import (
    get_tool_profile, save_tool_profile,
    save_chunk, vector_search,
)
from ingestion.chunker import chunk_readme, chunk_code

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM = (
    "You are a tool analyst. Extract structured metadata from this GitHub repo. "
    "Return only valid JSON with these fields: "
    "tool_name, one_line, use_cases, input_types, output_types, dependencies, difficulty, tags."
)





def summarize_repo(repo_name: str, readme_text: str, file_tree: list[str]) -> dict:
    """Call gpt-4.1-mini to generate a JSON tool profile. Returns dict (no DB writes)."""
    user_msg = (
        f"Repository: {repo_name}\n\n"
        f"README:\n{readme_text[:6000]}\n\n"
        f"File tree:\n" + "\n".join(file_tree[:50])
    )

    profile = {}
    for attempt in range(2):
        try:
            raw = openai_client.chat_router(
                agent="agent0",
                messages=[
                    {"role": "system", "content": SUMMARIZE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                json_mode=True,
            )
            profile = json.loads(raw)
            break
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 0:
                logger.warning(f"Summarize retry for {repo_name}: {e}")
            else:
                logger.error(f"Summarize failed for {repo_name}: {e}")

    return profile


def chunk_and_embed(repo_name: str, sections: list[dict], code_blocks: list[dict]):
    """Chunk + embed + upsert to Firestore (tool_profiles, readme_chunks, code_chunks)."""
    readme_chunks = chunk_readme(sections, repo_name)
    code_chunks = chunk_code(code_blocks, repo_name)

    # ── Profile embedding ───────────────────────────────────────────
    profile = get_tool_profile(repo_name)
    if profile:
        profile_text = json.dumps(profile)
        try:
            emb = openai_client.embed([profile_text])
            save_tool_profile(repo_name, profile, profile_text, emb[0])
        except Exception as e:
            logger.error(f"Profile embed failed for {repo_name}: {e}")

    # ── README chunk embeddings ─────────────────────────────────────
    non_empty = [c for c in readme_chunks if c.content.strip()]
    for i in range(0, len(non_empty), 100):
        batch = non_empty[i : i + 100]
        texts = [c.content for c in batch]
        try:
            embs = openai_client.embed(texts)
            for c, emb in zip(batch, embs):
                save_chunk(
                    c.id, c.repo_name, "readme", c.content, emb,
                    section_header=c.section_header,
                )
        except Exception as e:
            logger.error(f"README embed failed for {repo_name}: {e}")

    # ── Code chunk embeddings ───────────────────────────────────────
    non_empty_code = [c for c in code_chunks if c.content.strip()]
    for i in range(0, len(non_empty_code), 100):
        batch = non_empty_code[i : i + 100]
        texts = [c.content for c in batch]
        try:
            embs = openai_client.embed(texts)
            for c, emb in zip(batch, embs):
                save_chunk(
                    c.id, c.repo_name, "code", c.content, emb,
                    function_name=c.function_name,
                )
        except Exception as e:
            logger.error(f"Code embed failed for {repo_name}: {e}")

    logger.info(
        f"Embedded {repo_name}: {len(readme_chunks)} readme, "
        f"{len(code_chunks)} code, profile={'yes' if profile else 'no'}"
    )
