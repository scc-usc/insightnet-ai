"""
FastAPI server — /query, /ingest, /webhook/github, /health
"""

import hmac
import hashlib
import time
import logging

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from infra.db import supabase, OPENAI_API_KEY, GITHUB_WEBHOOK_SECRET, get_chroma_client
from infra.scraper import scrape_repo, save_repo, load_repo_list
from infra.updater import reingest_repo
from ingestion.parser import parse_readme, parse_code
from ingestion.summarizer import summarize_repo, chunk_and_embed
from retrieval.synthesis import run_query_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="InsightNet", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://insightnet-production.up.railway.app",
        "https://insightnet-eta.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
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


class QueryRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []


class IngestRequest(BaseModel):
    repo_url: str | None = None
    run_all: bool = False


# ── Routes ───────────────────────────────────────────────────────────

@app.post("/query")
async def query_endpoint(req: QueryRequest):
    history = [{"role": m.role, "content": m.content} for m in req.history]

    def generate():
        for item in run_query_pipeline(req.query, history):
            if isinstance(item, str):
                # Status marker
                yield item
            elif hasattr(item, "choices") and item.choices:
                delta = item.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest):
    if req.run_all:
        repos = load_repo_list("repos.txt")
        results = []
        for url in repos:
            record = scrape_repo(url)
            if record is None:
                results.append({"repo": url, "status": "skipped"})
                continue
            save_repo(record)
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
        save_repo(record)
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


@app.get("/health")
async def health():
    status = {}

    try:
        supabase.table("repos").select("repo_name").limit(1).execute()
        status["supabase"] = "ok"
    except Exception:
        status["supabase"] = "error"

    try:
        get_chroma_client().list_collections()
        status["chromadb"] = "ok"
    except Exception:
        status["chromadb"] = "error"

    status["openai"] = "ok" if OPENAI_API_KEY else "missing"
    return status
