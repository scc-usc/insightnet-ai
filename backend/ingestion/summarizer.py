"""
Agent 0 -- Tool Summarizer.

summarize_repo():  gpt-4.1-mini -> JSON tool profile (returned to caller, no DB writes)
chunk_and_embed(): used by updater for re-ingestion (writes to Supabase + ChromaDB)
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from infra import openai_client
from infra.db import supabase, col_profiles, col_readme, col_code
from ingestion.chunker import chunk_readme, chunk_code

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM = (
    "You are a tool analyst. Extract structured metadata from this GitHub repo. "
    "Return only valid JSON with these fields: "
    "tool_name, one_line, use_cases, input_types, output_types, dependencies, difficulty, tags."
)


def _chroma_upsert_safe(collection, timeout=60, **kwargs):
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(collection.upsert, **kwargs)
    try:
        future.result(timeout=timeout)
    except TimeoutError:
        logger.error(f"Chroma upsert timed out after {timeout}s")
    finally:
        pool.shutdown(wait=False)


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
    """Chunk + embed + upsert to ChromaDB. Used by updater re-ingestion."""
    readme_chunks = chunk_readme(sections, repo_name)
    code_chunks = chunk_code(code_blocks, repo_name)

    # Embed profile
    profile_text = ""
    result = (
        supabase.table("tool_profiles")
        .select("profile")
        .eq("repo_name", repo_name)
        .limit(1)
        .execute()
    )
    if result.data:
        profile_text = json.dumps(result.data[0].get("profile", {}))

    if profile_text:
        try:
            emb = openai_client.embed([profile_text])
            _chroma_upsert_safe(
                col_profiles,
                ids=[f"{repo_name}::profile"],
                documents=[profile_text],
                embeddings=emb,
                metadatas=[{"repo_name": repo_name, "chunk_type": "profile"}],
            )
        except Exception as e:
            logger.error(f"Profile embed failed for {repo_name}: {e}")

    # Embed README chunks
    non_empty = [c for c in readme_chunks if c.content.strip()]
    for i in range(0, len(non_empty), 100):
        batch = non_empty[i : i + 100]
        texts = [c.content for c in batch]
        ids = [c.id for c in batch]
        metas = [{"repo_name": c.repo_name, "chunk_type": "readme", "section_header": c.section_header} for c in batch]
        try:
            emb = openai_client.embed(texts)
            _chroma_upsert_safe(col_readme, ids=ids, documents=texts, embeddings=emb, metadatas=metas)
        except Exception as e:
            logger.error(f"README embed failed for {repo_name}: {e}")

    # Embed code chunks
    non_empty_code = [c for c in code_chunks if c.content.strip()]
    for i in range(0, len(non_empty_code), 100):
        batch = non_empty_code[i : i + 100]
        texts = [c.content for c in batch]
        ids = [c.id for c in batch]
        metas = [{"repo_name": c.repo_name, "chunk_type": "code", "function_name": c.function_name} for c in batch]
        try:
            emb = openai_client.embed(texts)
            _chroma_upsert_safe(col_code, ids=ids, documents=texts, embeddings=emb, metadatas=metas)
        except Exception as e:
            logger.error(f"Code embed failed for {repo_name}: {e}")

    logger.info(
        f"Embedded {repo_name}: {len(readme_chunks)} readme, "
        f"{len(code_chunks)} code, profile={'yes' if profile_text else 'no'}"
    )
