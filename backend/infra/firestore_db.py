"""
Firestore client — replaces Supabase REST + ChromaDB.

Provides:
  - Repo storage          (/repos)
  - Tool profiles         (/tool_profiles)  with Vector embeddings
  - README chunks         (/readme_chunks)  with Vector embeddings
  - Code chunks           (/code_chunks)    with Vector embeddings
  - Ingestion log         (/ingestion_log)
  - Rate-limit counters   (/rate_limits)    token-bucket, no Redis needed

Initialization priority:
  1. FIREBASE_SERVICE_ACCOUNT_JSON env var (JSON string)
  2. FIREBASE_SERVICE_ACCOUNT_FILE env var (path to .json file)
  3. Application Default Credentials (Cloud Run / gcloud auth application-default login)
"""

import os
import json
import logging
import time
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1 import transactional

logger = logging.getLogger(__name__)

_db = None


# ── Initialization ────────────────────────────────────────────────────

def _init_firebase():
    global _db
    if _db is not None:
        return _db

    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    sa_file = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE")

    try:
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
        elif sa_file:
            cred = credentials.Certificate(sa_file)
        else:
            # Cloud Run / local gcloud auth application-default login
            cred = credentials.ApplicationDefault()

        try:
            firebase_admin.initialize_app(cred)
        except ValueError:
            pass  # already initialized

        _db = firestore.client()
        logger.info("Firestore client initialized")
    except Exception as e:
        logger.error(f"Firestore init failed: {e}")
        raise

    return _db


def get_db():
    if _db is None:
        return _init_firebase()
    return _db


# ── Helpers ────────────────────────────────────────────────────────────

def encode_id(raw: str) -> str:
    """Encode a string containing '/' or '::' to a safe Firestore doc ID."""
    return raw.replace("/", "__").replace("::", "--")


# ── Repos ──────────────────────────────────────────────────────────────

def save_repo(record) -> None:
    """Upsert a RepoRecord to /repos/{id}. Large fields are truncated."""
    db = get_db()
    db.collection("repos").document(encode_id(record.repo_name)).set(
        {
            "repo_name": record.repo_name,
            "owner": record.owner,
            # Truncate to stay well within Firestore's 1 MiB doc limit
            "readme_text": record.readme_text[:4000],
            "commit_sha": record.commit_sha,
            "ingested_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def get_repo_sha(repo_name: str) -> str | None:
    db = get_db()
    doc = db.collection("repos").document(encode_id(repo_name)).get()
    return doc.to_dict().get("commit_sha") if doc.exists else None


def list_repo_names() -> list[str]:
    db = get_db()
    return [d.to_dict().get("repo_name", "") for d in db.collection("repos").stream()]


# ── Tool profiles ──────────────────────────────────────────────────────

def save_tool_profile(repo_name: str, profile: dict, content: str, embedding: list[float]) -> None:
    db = get_db()
    db.collection("tool_profiles").document(encode_id(repo_name)).set(
        {
            "repo_name": repo_name,
            "profile": profile,
            "content": content,
            "embedding": Vector(embedding),
            "chunk_type": "profile",
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def get_tool_profile(repo_name: str) -> dict | None:
    db = get_db()
    doc = db.collection("tool_profiles").document(encode_id(repo_name)).get()
    return doc.to_dict().get("profile") if doc.exists else None


# ── Chunks ────────────────────────────────────────────────────────────

def save_chunk(
    chunk_id: str,
    repo_name: str,
    chunk_type: str,           # "readme" | "code"
    content: str,
    embedding: list[float],
    section_header: str = "",
    function_name: str = "",
) -> None:
    collection_name = "readme_chunks" if chunk_type == "readme" else "code_chunks"
    get_db().collection(collection_name).document(encode_id(chunk_id)).set(
        {
            "chunk_id": chunk_id,
            "repo_name": repo_name,
            "chunk_type": chunk_type,
            "content": content,
            "embedding": Vector(embedding),
            "section_header": section_header,
            "function_name": function_name,
        }
    )


def delete_repo_chunks(repo_name: str) -> None:
    """Delete all Firestore entries for a repo (for re-ingestion)."""
    db = get_db()
    for col_name in ("tool_profiles", "readme_chunks", "code_chunks"):
        col = db.collection(col_name)
        for doc in col.where("repo_name", "==", repo_name).stream():
            doc.reference.delete()


# ── Vector search ─────────────────────────────────────────────────────

_COLLECTION_MAP = {
    "tool_profiles": "tool_profiles",
    "readme_chunks": "readme_chunks",
    "code_chunks": "code_chunks",
}


def vector_search(collection_name: str, query_embedding: list[float], limit: int = 10) -> list[dict]:
    """
    Approximate nearest-neighbor search using Firestore native vector search.
    Requires a vector index created with:

        gcloud firestore indexes composite create \\
          --collection-group=<collection_name> \\
          --query-scope=COLLECTION \\
          --field-config field-path=embedding,vector-config='{"dimension":512,"flat": {}}'
    """
    col_name = _COLLECTION_MAP.get(collection_name, collection_name)
    db = get_db()
    try:
        results = (
            db.collection(col_name)
            .find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_embedding),
                distance_measure=DistanceMeasure.COSINE,
                limit=limit,
            )
            .get()
        )
        return [doc.to_dict() for doc in results]
    except Exception as e:
        logger.error(f"Vector search failed on '{col_name}': {e}")
        return []


# ── Ingestion log ─────────────────────────────────────────────────────

def log_ingestion(repo_name: str, trigger: str, status: str, commit_sha: str = "") -> None:
    get_db().collection("ingestion_log").add(
        {
            "repo_name": repo_name,
            "trigger": trigger,
            "status": status,
            "commit_sha": commit_sha,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )


# ── Rate limiting (token bucket, Firestore-backed) ────────────────────

_MAX_TOKENS = 20        # max burst per user
_REFILL_PER_MIN = 5.0   # tokens replenished per minute
_QUERY_COST = 1         # tokens consumed per /query request


@transactional
def _consume_token(transaction, ref):
    """Transactionally consume one token. Returns True if allowed."""
    doc = ref.get(transaction=transaction)
    now = datetime.now(timezone.utc)

    if doc.exists:
        data = doc.to_dict()
        tokens = float(data.get("tokens", _MAX_TOKENS))
        last_refill = data.get("last_refill")
        if last_refill is not None:
            if hasattr(last_refill, "timestamp"):
                last_ts = last_refill.timestamp()
            else:
                last_ts = now.timestamp()
            elapsed_min = max(0.0, (now.timestamp() - last_ts) / 60.0)
            tokens = min(_MAX_TOKENS, tokens + elapsed_min * _REFILL_PER_MIN)
        else:
            tokens = _MAX_TOKENS
    else:
        tokens = _MAX_TOKENS

    if tokens < _QUERY_COST:
        return False

    transaction.set(
        ref,
        {"tokens": tokens - _QUERY_COST, "last_refill": now},
        merge=True,
    )
    return True


def check_rate_limit(uid: str) -> bool:
    """
    Token-bucket rate limiter. Returns True (allowed) or False (rate-limited).
    Fails open on DB error to avoid blocking users on transient outages.
    """
    db = get_db()
    ref = db.collection("rate_limits").document(encode_id(uid))
    try:
        return _consume_token(db.transaction(), ref)
    except Exception as e:
        logger.error(f"Rate limit check failed for uid={uid}: {e}")
        return True  # fail open
