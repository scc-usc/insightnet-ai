"""
Agent 2 — Multi-Collection Retrieval + Reciprocal Rank Fusion.

embed_query(query) → embedding vector (cached per MD5)
retrieve(query_plan, query_embedding, top_k) → top-20 RankedResults
"""

import hashlib
import logging
from collections import defaultdict

from infra import openai_client
from infra.firestore_db import vector_search
from models import QueryPlan, RankedResult

logger = logging.getLogger(__name__)

_embed_cache: dict[str, list[float]] = {}

_COLLECTION_NAMES = {"tool_profiles", "readme_chunks", "code_chunks"}


def embed_query(query: str) -> list[float]:
    key = hashlib.md5(query.encode()).hexdigest()
    if key in _embed_cache:
        return _embed_cache[key]
    result = openai_client.embed([query])
    _embed_cache[key] = result[0]
    return result[0]


def retrieve(query_plan: QueryPlan, query_embedding: list[float], top_k: int = 10) -> list[RankedResult]:
    """Query each preferred collection via Firestore vector search, apply RRF, return top-20."""
    all_hits: list[tuple[str, str, str, int]] = []  # (repo_name, chunk_text, collection, rank)

    for col_name in query_plan.preferred_collections:
        if col_name not in _COLLECTION_NAMES:
            continue
        try:
            docs = vector_search(col_name, query_embedding, limit=top_k)
            for rank, doc in enumerate(docs):
                repo = doc.get("repo_name", "unknown")
                text = doc.get("content", "")
                all_hits.append((repo, text, col_name, rank))
        except Exception as e:
            logger.error(f"Query failed for {col_name}: {e}")

    # ── Reciprocal Rank Fusion: score(d) = Σ 1/(60 + rank_i) ────────
    rrf: dict[str, float] = defaultdict(float)
    best: dict[str, tuple[str, str]] = {}  # repo → (chunk_text, collection)
    best_score: dict[str, float] = {}  # repo → best individual hit score

    for repo, text, col_name, rank in all_hits:
        score = 1.0 / (60 + rank)
        rrf[repo] += score
        if repo not in best or score > best_score.get(repo, 0.0):
            best[repo] = (text, col_name)
            best_score[repo] = score

    ranked = []
    for repo, score in sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:20]:
        text, col_name = best[repo]
        ranked.append(RankedResult(
            repo_name=repo,
            chunk_text=text,
            score=score,
            source_collection=col_name,
        ))

    return ranked
