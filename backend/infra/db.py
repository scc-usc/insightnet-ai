"""
Supabase REST wrapper (no SDK — avoids async/event-loop hangs)
+ ChromaDB Cloud lazy initialization.
"""

import os
import logging

from dotenv import load_dotenv
import httpx

load_dotenv()

logger = logging.getLogger(__name__)

# ── Environment variables ────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY", "")
CHROMA_TENANT = os.getenv("CHROMA_TENANT", "")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "")

# ── Persistent HTTP client with explicit timeouts ────────────────────
_http = httpx.Client(timeout=httpx.Timeout(30, connect=10))


# ── Lightweight Supabase REST wrapper ────────────────────────────────
class _TableResult:
    def __init__(self, data):
        self.data = data


class _TableQuery:
    def __init__(self, base: str, headers: dict, table: str):
        self._url = f"{base}/{table}"
        self._headers = dict(headers)
        self._params: dict = {}
        self._body = None
        self._method = "GET"

    # ── query builders ──
    def select(self, cols: str = "*"):
        self._params["select"] = cols
        return self

    def eq(self, col: str, val):
        self._params[col] = f"eq.{val}"
        return self

    def limit(self, n: int):
        self._headers["Range"] = f"0-{n - 1}"
        return self

    def range(self, start: int, end: int):
        self._headers["Range"] = f"{start}-{end}"
        return self

    def upsert(self, data):
        self._method = "POST"
        self._headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        self._body = data if isinstance(data, list) else [data]
        return self

    def insert(self, data):
        self._method = "POST"
        self._headers["Prefer"] = "return=representation"
        self._body = data if isinstance(data, list) else [data]
        return self

    def execute(self):
        if self._method == "POST":
            r = _http.post(self._url, headers=self._headers, json=self._body)
        else:
            r = _http.get(self._url, headers=self._headers, params=self._params)
        r.raise_for_status()
        return _TableResult(r.json())


class _SupabaseREST:
    def __init__(self, url: str, key: str):
        self.base = f"{url}/rest/v1"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def table(self, name: str):
        return _TableQuery(self.base, self._headers, name)


supabase = _SupabaseREST(SUPABASE_URL, SUPABASE_KEY)


# ── ChromaDB Cloud — lazy init (connects on first use) ───────────────
_chroma_client = None
_collections: dict = {}


def _init_chroma():
    global _chroma_client
    if _chroma_client is not None:
        return
    import chromadb
    logger.info("Connecting to ChromaDB Cloud...")
    _chroma_client = chromadb.CloudClient(
        api_key=CHROMA_API_KEY,
        tenant=CHROMA_TENANT,
        database=CHROMA_DATABASE,
    )
    for name in ("tool_profiles", "readme_chunks", "code_chunks"):
        _collections[name] = _chroma_client.get_or_create_collection(name)
    logger.info("ChromaDB Cloud connected (3 collections ready)")


class _LazyCollection:
    """Proxy that delays ChromaDB connection until first attribute access."""

    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr):
        _init_chroma()
        return getattr(_collections[self._name], attr)


col_profiles = _LazyCollection("tool_profiles")
col_readme = _LazyCollection("readme_chunks")
col_code = _LazyCollection("code_chunks")


def get_chroma_client():
    """Return the underlying ChromaDB client (for health checks)."""
    _init_chroma()
    return _chroma_client
