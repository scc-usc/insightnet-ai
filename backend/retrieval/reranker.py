"""
Agent 3 — Re-Ranking.

Stage A: cosine similarity re-score (top-20 → top-10)
Stage B: o3 judge — single batch call (top-10 → top-5), cached per MD5(query)
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone

from infra import openai_client
from models import RankedResult

logger = logging.getLogger(__name__)

JUDGE_CACHE_FILE = "judge_cache.json"
CACHE_TTL = 86400  # 24 hours


def _load_cache() -> dict:
    if os.path.exists(JUDGE_CACHE_FILE):
        with open(JUDGE_CACHE_FILE) as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    with open(JUDGE_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# ── Stage A: cosine re-score ─────────────────────────────────────────

def cosine_rerank(query_emb: list[float], results: list[RankedResult], top_n: int = 10) -> list[RankedResult]:
    # Firestore vector_search already scores by cosine similarity — sort and trim.
    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
    return sorted_results[:top_n]


# ── Stage B: o3 judge ────────────────────────────────────────────────

def llm_judge(query: str, candidates: list[RankedResult]) -> list[RankedResult]:
    cache_key = hashlib.md5(query.encode()).hexdigest()
    cache = _load_cache()

    # Check cache with TTL
    if cache_key in cache:
        entry = cache[cache_key]
        cached_at = datetime.fromisoformat(entry["timestamp"])
        if (datetime.now(timezone.utc) - cached_at).total_seconds() < CACHE_TTL:
            scores = {item["id"]: item for item in entry["scores"]}
            for c in candidates:
                if c.repo_name in scores:
                    c.score = scores[c.repo_name]["score"]
                    c.reason = scores[c.repo_name].get("reason", "")
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:5]

    numbered = "\n".join(
        f"{i+1}. {c.repo_name}: {c.chunk_text[:300]}"
        for i, c in enumerate(candidates)
    )

    try:
        raw = openai_client.chat_router(
            agent="agent3",
            messages=[
                {"role": "system", "content": "Score each candidate 1-10 for relevance to the query. Return a JSON array of {id, score, reason}."},
                {"role": "user", "content": f"Query: {query}\n\nCandidates:\n{numbered}"},
            ],
            json_mode=True,
        )
        scores_list = json.loads(raw)
        if isinstance(scores_list, dict):
            scores_list = scores_list.get("results", scores_list.get("scores", []))

        cache[cache_key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scores": scores_list,
        }
        _save_cache(cache)

        score_map = {item["id"]: item for item in scores_list}
        for c in candidates:
            if c.repo_name in score_map:
                c.score = score_map[c.repo_name]["score"]
                c.reason = score_map[c.repo_name].get("reason", "")

    except Exception as e:
        logger.error(f"LLM judge failed: {e}")

    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:5]


# ── Combined rerank ──────────────────────────────────────────────────

def rerank(query: str, query_emb: list[float], results: list[RankedResult]) -> list[RankedResult]:
    top10 = cosine_rerank(query_emb, results, top_n=10)
    top5 = llm_judge(query, top10)
    return top5
