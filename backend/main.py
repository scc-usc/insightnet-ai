"""
InsightNet CLI -- three-phase pipeline, fully local until migration.

  python main.py --ingest     Phase 1: scrape + summarize + chunk -> local JSON
  python main.py --embed      Phase 2: embed local chunks -> local JSON
  python main.py --migrate    Phase 3: push all local data to Supabase + ChromaDB Cloud
  python main.py --serve      Start FastAPI server
  python main.py --update     Check repos for updates (one-shot)
  python main.py --schedule   Run daily update scheduler
"""

import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

# Load .env before any infra imports so Firebase/OpenAI creds are available
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for lib in ("httpx", "httpcore", "chromadb", "openai", "urllib3"):
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("main")

# Local data files
DATA_DIR = "data"
REPOS_FILE = os.path.join(DATA_DIR, "repos.json")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
CHUNKS_FILE = os.path.join(DATA_DIR, "chunks.json")
EMBEDDINGS_FILE = os.path.join(DATA_DIR, "embeddings.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str) -> list | dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_json(path: str, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# =====================================================================
#  Phase 1: Scrape + Summarize + Chunk  (network: GitHub + OpenAI only)
# =====================================================================

def _process_one(url: str, idx: int, total: int, all_repos: dict, all_profiles: dict, all_chunks: list, chunk_ids: set) -> str:
    """Scrape -> summarize -> chunk -> append to in-memory dicts/lists."""
    from infra.scraper import scrape_repo
    from ingestion.parser import parse_readme, parse_code
    from ingestion.chunker import chunk_readme, chunk_code
    from ingestion.summarizer import summarize_repo

    tag = f"[{idx}/{total}]"
    parts = url.rstrip("/").split("/")
    repo_name = f"{parts[-2]}/{parts[-1]}"

    try:
        if repo_name in all_profiles:
            return "SKIP (already ingested)"

        # 1. Scrape (GitHub network)
        print(f"  {tag} Scraping...", flush=True)
        record = scrape_repo(url)
        if record is None:
            return "SKIP (README missing or too short)"

        # 2. Save repo data in memory
        all_repos[record.repo_name] = {
            "repo_name": record.repo_name,
            "owner": record.owner,
            "readme_text": record.readme_text,
            "file_contents": record.file_contents,
            "commit_sha": record.commit_sha,
        }

        # 3. Summarize with gpt-4.1-mini (OpenAI network)
        print(f"  {tag} Summarizing...", flush=True)
        profile = summarize_repo(record.repo_name, record.readme_text, list(record.file_contents.keys()))
        if profile:
            all_profiles[record.repo_name] = profile

        # 4. Parse + chunk (pure CPU, instant)
        print(f"  {tag} Chunking...", flush=True)
        sections = parse_readme(record.readme_text)
        readme_chunks = chunk_readme(sections, record.repo_name)

        code_blocks = []
        for filename, content in record.file_contents.items():
            code_blocks.extend(parse_code(filename, content))
        code_chunks = chunk_code(code_blocks, record.repo_name)

        # 5. Append chunks (uses shared set for O(1) dedup)
        for c in readme_chunks:
            if c.id not in chunk_ids:
                all_chunks.append({
                    "id": c.id, "repo_name": c.repo_name, "chunk_type": c.chunk_type,
                    "content": c.content, "section_header": c.section_header, "function_name": "",
                })
                chunk_ids.add(c.id)
        for c in code_chunks:
            if c.id not in chunk_ids:
                all_chunks.append({
                    "id": c.id, "repo_name": c.repo_name, "chunk_type": c.chunk_type,
                    "content": c.content, "section_header": "", "function_name": c.function_name,
                })
                chunk_ids.add(c.id)

        return f"OK -- {len(readme_chunks)} readme + {len(code_chunks)} code chunks"

    except Exception as e:
        logger.exception(f"Failed: {url}")
        return f"FAILED -- {e}"


def ingest_all():
    """Phase 1: scrape + summarize + chunk -> local JSON files."""
    from infra.scraper import load_repo_list

    repos_urls = load_repo_list("repos.txt")
    print(f"\n{'='*60}")
    print(f"  Phase 1: Scrape + Summarize + Chunk ({len(repos_urls)} repos)")
    print(f"  Everything saved locally to {DATA_DIR}/")
    print(f"{'='*60}\n")

    # Load existing data (resume support)
    all_repos = _load_json(REPOS_FILE) or {}
    all_profiles = _load_json(PROFILES_FILE) or {}
    all_chunks = _load_json(CHUNKS_FILE) or []
    chunk_ids = {c["id"] for c in all_chunks}  # fast dedup set

    t0 = time.time()
    ok = skip = fail = 0

    for i, url in enumerate(repos_urls):
        print(f"\n[{i+1}/{len(repos_urls)}] {url}", flush=True)
        result = _process_one(url, i + 1, len(repos_urls), all_repos, all_profiles, all_chunks, chunk_ids)

        if result.startswith("OK"):
            ok += 1
        elif result.startswith("SKIP"):
            skip += 1
        else:
            fail += 1

        print(f"  -> {result}", flush=True)

        # Save every 5 repos (balances crash-safety vs speed)
        if (i + 1) % 5 == 0 or (i + 1) == len(repos_urls):
            print(f"  Saving to disk...", flush=True)
            _save_json(REPOS_FILE, all_repos)
            _save_json(PROFILES_FILE, all_profiles)
            _save_json(CHUNKS_FILE, all_chunks)

    # Final save
    _save_json(REPOS_FILE, all_repos)
    _save_json(PROFILES_FILE, all_profiles)
    _save_json(CHUNKS_FILE, all_chunks)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Phase 1 complete in {elapsed:.0f}s")
    print(f"  {ok} ok, {skip} skipped, {fail} failed")
    print(f"  {len(all_repos)} repos, {len(all_profiles)} profiles, {len(all_chunks)} chunks")
    print(f"  Next: python main.py --embed")
    print(f"{'='*60}\n")


# =====================================================================
#  Phase 2: Embed  (network: OpenAI only, saves locally)
# =====================================================================

def embed_all():
    """Phase 2: read local data -> embed with OpenAI -> save embeddings locally."""
    from infra import openai_client

    print(f"\n{'='*60}")
    print(f"  Phase 2: Embed (OpenAI) -> local {EMBEDDINGS_FILE}")
    print(f"{'='*60}\n")

    profiles = _load_json(PROFILES_FILE) or {}
    chunks = _load_json(CHUNKS_FILE) or []

    # Load existing embeddings (resume support)
    embeddings = _load_json(EMBEDDINGS_FILE)
    if not isinstance(embeddings, dict):
        embeddings = {"profiles": {}, "chunks": {}}
    if "profiles" not in embeddings:
        embeddings["profiles"] = {}
    if "chunks" not in embeddings:
        embeddings["chunks"] = {}

    # ── Embed profiles ───────────────────────────────────────────────
    profile_items = [(name, json.dumps(prof)) for name, prof in profiles.items() if name not in embeddings["profiles"]]
    print(f"Profiles to embed: {len(profile_items)} (skipping {len(profiles) - len(profile_items)} already done)", flush=True)

    for i, (repo_name, text) in enumerate(profile_items):
        try:
            emb = openai_client.embed([text])
            embeddings["profiles"][repo_name] = {
                "id": f"{repo_name}::profile",
                "text": text,
                "embedding": emb[0],
                "metadata": {"repo_name": repo_name, "chunk_type": "profile"},
            }
            print(f"  [{i+1}/{len(profile_items)}] {repo_name}", flush=True)
        except Exception as e:
            print(f"  [{i+1}/{len(profile_items)}] FAILED {repo_name}: {e}", flush=True)

        # Save periodically
        if (i + 1) % 10 == 0:
            _save_json(EMBEDDINGS_FILE, embeddings)

    # ── Embed chunks ─────────────────────────────────────────────────
    to_embed = [c for c in chunks if c["content"].strip() and c["id"] not in embeddings["chunks"]]
    print(f"\nChunks to embed: {len(to_embed)} (skipping {len(chunks) - len(to_embed)} already done)", flush=True)

    for bi in range(0, len(to_embed), 100):
        batch = to_embed[bi : bi + 100]
        texts = [c["content"] for c in batch]
        try:
            embs = openai_client.embed(texts)
            for j, c in enumerate(batch):
                embeddings["chunks"][c["id"]] = {
                    "id": c["id"],
                    "text": c["content"],
                    "embedding": embs[j],
                    "chunk_type": c["chunk_type"],
                    "metadata": {
                        "repo_name": c["repo_name"],
                        "chunk_type": c["chunk_type"],
                        "section_header": c.get("section_header", ""),
                        "function_name": c.get("function_name", ""),
                    },
                }
            print(f"  [{min(bi+100, len(to_embed))}/{len(to_embed)}] embedded", flush=True)
        except Exception as e:
            logger.error(f"Embed batch failed at {bi}: {e}")

        # Save every 5 batches (embeddings file gets large)
        if ((bi // 100) + 1) % 5 == 0:
            print(f"    saving embeddings to disk...", flush=True)
            _save_json(EMBEDDINGS_FILE, embeddings)

    _save_json(EMBEDDINGS_FILE, embeddings)

    print(f"\n{'='*60}")
    print(f"  Phase 2 complete")
    print(f"  {len(embeddings['profiles'])} profile embeddings")
    print(f"  {len(embeddings['chunks'])} chunk embeddings")
    print(f"  Next: python main.py --migrate")
    print(f"{'='*60}\n")


# =====================================================================
#  Phase 3: Migrate  (push everything to Firestore)
# =====================================================================

def migrate_all():
    """Phase 3: push local JSON data to Firestore (replaces Supabase + ChromaDB)."""
    from infra.firestore_db import (
        get_db, encode_id, save_repo as _fs_save_repo,
        save_tool_profile, save_chunk, log_ingestion,
    )
    from models import RepoRecord
    from google.cloud.firestore_v1.vector import Vector
    import firebase_admin

    repos_data = _load_json(REPOS_FILE) or {}
    profiles = _load_json(PROFILES_FILE) or {}
    embeddings = _load_json(EMBEDDINGS_FILE) or {}

    print(f"\n{'='*60}")
    print(f"  Phase 3: Migrate to Firestore")
    print(f"  {len(repos_data)} repos, {len(profiles)} profiles,")
    print(f"  {len(embeddings.get('profiles', {}))} profile embeddings,")
    print(f"  {len(embeddings.get('chunks', {}))} chunk embeddings")
    print(f"{'='*60}\n")

    db = get_db()

    # ── Firestore: repos ─────────────────────────────────────────────
    print("Uploading repos to Firestore /repos...", flush=True)
    for i, (repo_name, data) in enumerate(repos_data.items()):
        try:
            record = RepoRecord(
                repo_name=data["repo_name"],
                owner=data.get("owner", ""),
                readme_text=data.get("readme_text", ""),
                commit_sha=data.get("commit_sha", ""),
            )
            _fs_save_repo(record)
            if (i + 1) % 10 == 0:
                print(f"  repos: {i+1}/{len(repos_data)}", flush=True)
        except Exception as e:
            logger.error(f"Repo upload failed for {repo_name}: {e}")
    print(f"  repos done ({len(repos_data)})", flush=True)

    # ── Firestore: tool_profiles (without embeddings) ────────────────
    print("Uploading tool profiles to Firestore /tool_profiles...", flush=True)
    for i, (repo_name, profile) in enumerate(profiles.items()):
        try:
            # We store without embedding here; Phase 2 adds embedding separately
            db.collection("tool_profiles").document(encode_id(repo_name)).set(
                {"repo_name": repo_name, "profile": profile, "content": json.dumps(profile)},
                merge=True,
            )
            if (i + 1) % 10 == 0:
                print(f"  profiles: {i+1}/{len(profiles)}", flush=True)
        except Exception as e:
            logger.error(f"Profile upload failed for {repo_name}: {e}")
    print(f"  profiles done ({len(profiles)})", flush=True)

    # ── Firestore: profile embeddings ────────────────────────────────
    print("Uploading profile embeddings to Firestore /tool_profiles...", flush=True)
    prof_embs = embeddings.get("profiles", {})
    for i, (repo_name, entry) in enumerate(prof_embs.items()):
        try:
            db.collection("tool_profiles").document(encode_id(repo_name)).set(
                {"embedding": Vector(entry["embedding"])},
                merge=True,
            )
            if (i + 1) % 20 == 0:
                print(f"  profile embeddings: {i+1}/{len(prof_embs)}", flush=True)
        except Exception as e:
            logger.error(f"Profile embedding failed for {repo_name}: {e}")
    print(f"  profile embeddings done ({len(prof_embs)})", flush=True)

    # ── Firestore: chunk embeddings ───────────────────────────────────
    chunk_embs = embeddings.get("chunks", {})
    readme_embs = {k: v for k, v in chunk_embs.items() if v.get("chunk_type") == "readme"}
    code_embs = {k: v for k, v in chunk_embs.items() if v.get("chunk_type") == "code"}

    for label, embs_dict, col_name in [
        ("readme", readme_embs, "readme_chunks"),
        ("code", code_embs, "code_chunks"),
    ]:
        print(f"Uploading {label} chunk embeddings to Firestore /{col_name}...", flush=True)
        items = list(embs_dict.items())
        for i, (chunk_id, entry) in enumerate(items):
            try:
                meta = entry.get("metadata", {})
                db.collection(col_name).document(encode_id(chunk_id)).set({
                    "chunk_id": chunk_id,
                    "repo_name": meta.get("repo_name", ""),
                    "chunk_type": entry.get("chunk_type", label),
                    "content": entry.get("text", ""),
                    "embedding": Vector(entry["embedding"]),
                    "section_header": meta.get("section_header", ""),
                    "function_name": meta.get("function_name", ""),
                })
                if (i + 1) % 50 == 0:
                    print(f"  {label} chunks: {i+1}/{len(items)}", flush=True)
            except Exception as e:
                logger.error(f"{label} chunk upload failed {chunk_id}: {e}")
        print(f"  {label} chunks done ({len(items)})", flush=True)

    print(f"\n{'='*60}")
    print(f"  Phase 3 complete — all data pushed to Firestore")
    print(f"  Next: create vector indexes with the commands in .env.example")
    print(f"{'='*60}\n")


# =====================================================================
#  CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="InsightNet CLI")
    parser.add_argument("--ingest", action="store_true", help="Phase 1: scrape + summarize + chunk -> local")
    parser.add_argument("--embed", action="store_true", help="Phase 2: embed local data -> local")
    parser.add_argument("--migrate", action="store_true", help="Phase 3: push local -> Supabase + ChromaDB")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI server")
    parser.add_argument("--update", action="store_true", help="Check repos for updates (one-shot)")
    parser.add_argument("--schedule", action="store_true", help="Run daily update scheduler")
    args = parser.parse_args()

    if args.ingest:
        ingest_all()
        os._exit(0)
    elif args.embed:
        embed_all()
        os._exit(0)
    elif args.migrate:
        migrate_all()
        os._exit(0)
    elif args.serve:
        import uvicorn
        uvicorn.run("infra.server:app", host="0.0.0.0", port=8000, reload=True)
    elif args.update:
        from infra.updater import check_for_updates
        from infra.scraper import load_repo_list
        check_for_updates(load_repo_list("repos.txt"))
    elif args.schedule:
        from infra.updater import start_scheduler
        start_scheduler()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
