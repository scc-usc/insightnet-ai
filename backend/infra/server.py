"""
FastAPI server — /query, /ingest, /webhook/github, /health

Auth:    Firebase ID token in Authorization: Bearer header (all endpoints)
         /ingest additionally requires ADMIN_UIDS membership
Rate:    Per-user token bucket enforced in infra/auth.py via Firestore
SSRF:    repo_url validated to github.com only
Models:  read from Firestore config/settings.model; any OpenRouter model ID allowed
"""

import hmac
import hashlib
import os
import re
import time
import logging

from fastapi import Depends, FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from infra.db import OPENROUTER_API_KEY, GITHUB_WEBHOOK_SECRET
from infra.firestore_db import get_db
from infra.auth import require_user, require_admin
from infra.scraper import scrape_repo, load_repo_list
from infra.scraper import save_repo as _save_repo_scraper
from infra.updater import reingest_repo
from ingestion.parser import parse_readme, parse_code
from ingestion.summarizer import summarize_repo, chunk_and_embed
from retrieval.synthesis import run_query_pipeline

logger = logging.getLogger(__name__)

# ── Allowed frontend origins ─────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "https://insightnet-ai.web.app",
    "https://insightnet-ai.firebaseapp.com",
]
# Also allow any extra origins from the env var (e.g. custom domain)
_extra = os.getenv("FRONTEND_URL", "")
_ALLOWED_ORIGINS += [o.strip() for o in _extra.split(",") if o.strip()]
# Always allow localhost in dev
if os.getenv("ENV", "production") != "production":
    _ALLOWED_ORIGINS += ["http://localhost:3000", "http://127.0.0.1:3000"]

# ── Model config (read from Firestore, cached per process) ──────────
_DEFAULT_MODEL = "openai/gpt-oss-120b"
_cached_model: str | None = None

def _get_model() -> str:
    """Return the model ID stored in Firestore config/settings, or the default."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    try:
        doc = get_db().collection("config").document("settings").get()
        if doc.exists:
            val = doc.to_dict().get("model")
            if val and isinstance(val, str):
                _cached_model = val
                return _cached_model
    except Exception as exc:
        logger.warning("Could not read model from Firestore config: %s", exc)
    _cached_model = _DEFAULT_MODEL
    return _cached_model

# ── GitHub repo URL pattern (SSRF guard) ─────────────────────────────
_GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+/?$"
)

app = FastAPI(title="Insight Net AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)



# ── Middleware ────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    ms = (time.time() - t0) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms)")
    return response


# ── Request models ───────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("user", "assistant", "system"):
            raise ValueError("role must be user, assistant, or system")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if len(v) > 8000:
            raise ValueError("message content exceeds 8000 characters")
        return v


class QueryRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("query must not be empty")
        if len(v) > 2000:
            raise ValueError("query exceeds 2000 characters")
        return v

    @field_validator("history")
    @classmethod
    def validate_history(cls, v):
        if len(v) > 40:
            raise ValueError("history exceeds 40 messages")
        return v


class IngestRequest(BaseModel):
    repo_url: str | None = None
    run_all: bool = False

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v):
        if v is not None and not _GITHUB_REPO_RE.match(v):
            raise ValueError("repo_url must be a valid https://github.com/{owner}/{repo} URL")
        return v


# ── Routes ───────────────────────────────────────────────────────────

@app.post("/query")
async def query_endpoint(req: QueryRequest, uid: str = Depends(require_user)):
    history = [{"role": m.role, "content": m.content} for m in req.history]
    model = _get_model()

    def generate():
        for item in run_query_pipeline(req.query, history, model=model):
            if isinstance(item, str):
                yield item
            elif hasattr(item, "choices") and item.choices:
                delta = item.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest, uid: str = Depends(require_admin)):
    if req.run_all:
        repos = load_repo_list("repos.txt")
        results = []
        for url in repos:
            record = scrape_repo(url)
            if record is None:
                results.append({"repo": url, "status": "skipped"})
                continue
            _save_repo_scraper(record)
            sections = parse_readme(record.readme_text)
            code_blocks = []
            for fn, content in record.file_contents.items():
                code_blocks.extend(parse_code(fn, content))
            summarize_repo(record.repo_name, record.readme_text, list(record.file_contents.keys()))
            chunk_and_embed(record.repo_name, sections, code_blocks)
            results.append({"repo": record.repo_name, "status": "ok"})
        return {"status": "ok", "results": results}

    if req.repo_url:
        record = scrape_repo(req.repo_url)
        if record is None:
            raise HTTPException(status_code=400, detail="Could not scrape repo")
        _save_repo_scraper(record)
        sections = parse_readme(record.readme_text)
        code_blocks = []
        for fn, content in record.file_contents.items():
            code_blocks.extend(parse_code(fn, content))
        summarize_repo(record.repo_name, record.readme_text, list(record.file_contents.keys()))
        chunk_and_embed(record.repo_name, sections, code_blocks)
        return {"status": "ok", "repo": record.repo_name}

    raise HTTPException(status_code=400, detail="Provide repo_url or set run_all=true")


@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """GitHub push webhook — HMAC-verified, no user auth required."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not GITHUB_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    repo_name = payload.get("repository", {}).get("full_name")
    if not repo_name:
        raise HTTPException(status_code=400, detail="Missing repository.full_name")

    background_tasks.add_task(reingest_repo, repo_name)
    return {"status": "queued", "repo": repo_name}


@app.get("/model")
async def model_endpoint(uid: str = Depends(require_user)):
    """Return the currently configured model ID."""
    global _cached_model
    _cached_model = None  # force re-read so callers always get the latest
    return {"model": _get_model()}


@app.get("/health")
async def health():
    status: dict = {}
    try:
        get_db().collection("repos").limit(1).get()
        status["firestore"] = "ok"
    except Exception:
        status["firestore"] = "error"

    status["openrouter"] = "ok" if OPENROUTER_API_KEY else "missing"
    return status

