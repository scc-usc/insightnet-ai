"""
Repo Update Detector — commit SHA polling + re-ingestion.

check_for_updates(): one-shot check all repos
reingest_repo():     re-scrape → delete stale Chroma entries → re-ingest
start_scheduler():   daily cron at 02:00
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import httpx
import schedule

from infra.db import GITHUB_TOKEN
from infra.firestore_db import get_repo_sha, log_ingestion, delete_repo_chunks, list_repo_names
from infra.scraper import load_repo_list, scrape_repo, save_repo
from ingestion.parser import parse_readme, parse_code
from ingestion.summarizer import summarize_repo, chunk_and_embed

logger = logging.getLogger(__name__)

_gh = httpx.Client(
    timeout=httpx.Timeout(30, connect=10),
    headers={"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {},
)


def _get_latest_sha(repo_name: str) -> str | None:
    try:
        resp = _gh.get(f"https://api.github.com/repos/{repo_name}/commits?per_page=1")
        if resp.status_code == 200:
            data = resp.json()
            if data:
                return data[0]["sha"]
    except Exception as e:
        logger.error(f"Failed to get SHA for {repo_name}: {e}")
    return None


def _get_stored_sha(repo_name: str) -> str | None:
    return get_repo_sha(repo_name)


def _log_ingestion(repo_name: str, trigger: str, status: str, commit_sha: str = ""):
    try:
        log_ingestion(repo_name, trigger, status, commit_sha)
    except Exception as e:
        logger.error(f"Failed to log ingestion for {repo_name}: {e}")


def reingest_repo(repo_name: str):
    """Full re-ingestion: scrape → delete old Chroma → summarize → chunk → embed."""
    logger.info(f"Re-ingesting {repo_name}...")
    record = scrape_repo(f"https://github.com/{repo_name}")
    if record is None:
        logger.warning(f"Re-ingest failed for {repo_name}: scrape returned None")
        _log_ingestion(repo_name, "update", "failed")
        return

    delete_repo_chunks(repo_name)
    save_repo(record)

    sections = parse_readme(record.readme_text)
    code_blocks = []
    for fn, content in record.file_contents.items():
        code_blocks.extend(parse_code(fn, content))

    summarize_repo(record.repo_name, record.readme_text, list(record.file_contents.keys()))
    chunk_and_embed(record.repo_name, sections, code_blocks)

    _log_ingestion(record.repo_name, "update", "success", record.commit_sha)
    logger.info(f"Re-ingested {repo_name}")


def check_for_updates(repo_list: list[str]):
    """One-shot: compare commit SHA for each repo, re-ingest if changed."""
    for url in repo_list:
        parts = url.rstrip("/").split("/")
        repo_name = f"{parts[-2]}/{parts[-1]}"

        latest = _get_latest_sha(repo_name)
        stored = _get_stored_sha(repo_name)

        if latest and latest != stored:
            logger.info(f"Update detected: {repo_name}")
            reingest_repo(repo_name)
        else:
            logger.info(f"No update: {repo_name}")
            _log_ingestion(repo_name, "scheduled_check", "skipped")

        time.sleep(0.5)


def start_scheduler():
    """Run daily update check at 02:00."""
    repos = load_repo_list("repos.txt")
    schedule.every().day.at("02:00").do(check_for_updates, repos)
    logger.info("Scheduler started — daily checks at 02:00")
    while True:
        schedule.run_pending()
        time.sleep(60)
