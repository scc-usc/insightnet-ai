"""
GitHub scraper — streams README + code files into memory, saves to Supabase.
Respects 5 000 req/hr GitHub limit with exponential backoff on 429.
"""

import time
import logging

import httpx

from models import RepoRecord
from infra.db import GITHUB_TOKEN
from infra.firestore_db import save_repo as _fs_save_repo

logger = logging.getLogger(__name__)

_gh = httpx.Client(
    timeout=httpx.Timeout(20, connect=10),
    headers={"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {},
)

ALLOWED_EXT = (".py", ".R", ".js", ".ts")


def load_repo_list(path: str = "repos.txt") -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def _parse_owner_repo(url: str) -> tuple[str, str]:
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def _github_get(url: str) -> httpx.Response | None:
    """GET with one retry on 429."""
    for attempt in range(2):
        try:
            resp = _gh.get(url)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            logger.warning(f"GitHub request failed: {url} — {e}")
            return None
        if resp.status_code == 429:
            if attempt == 0:
                logger.warning("GitHub 429 — waiting 60 s")
                time.sleep(60)
                continue
            return None
        return resp
    return None


def scrape_repo(repo_url: str) -> RepoRecord | None:
    owner, repo = _parse_owner_repo(repo_url)
    repo_name = f"{owner}/{repo}"

    # ── README ───────────────────────────────────────────────────────
    readme_text = ""
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        resp = _github_get(url)
        if resp and resp.status_code == 200:
            readme_text = resp.text
            break
        time.sleep(0.05)

    if not readme_text or len(readme_text) < 200:
        logger.info(f"Skipping {repo_name}: README missing or < 200 chars")
        return None

    time.sleep(0.05)

    # ── File tree (top-level code files, max 10) ────────────────────
    file_contents: dict[str, str] = {}
    used_branch = "main"
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
    resp = _github_get(tree_url)
    if resp and resp.status_code != 200:
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
        used_branch = "master"
        time.sleep(0.05)
        resp = _github_get(tree_url)

    if resp and resp.status_code == 200:
        tree = resp.json().get("tree", [])
        candidates = [
            item["path"]
            for item in tree
            if item["type"] == "blob"
            and any(item["path"].endswith(ext) for ext in ALLOWED_EXT)
            and item["path"].count("/") <= 2
        ]
        for fp in candidates[:10]:
            time.sleep(0.05)
            raw = _github_get(
                f"https://raw.githubusercontent.com/{owner}/{repo}/{used_branch}/{fp}"
            )
            if raw and raw.status_code == 200:
                file_contents[fp] = raw.text

    time.sleep(0.05)

    # ── Latest commit SHA ────────────────────────────────────────────
    commit_sha = ""
    resp = _github_get(f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1")
    if resp and resp.status_code == 200:
        commits = resp.json()
        if commits:
            commit_sha = commits[0]["sha"]

    return RepoRecord(
        repo_name=repo_name,
        owner=owner,
        readme_text=readme_text,
        file_contents=file_contents,
        commit_sha=commit_sha,
    )


def save_repo(record: RepoRecord):
    """Upsert scraped repo metadata to Firestore /repos collection."""
    _fs_save_repo(record)


def get_readme(repo_name: str) -> str:
    """Read README from Firestore (used by Agent 4)."""
    from infra.firestore_db import get_db, encode_id
    db = get_db()
    doc = db.collection("repos").document(encode_id(repo_name)).get()
    return doc.to_dict().get("readme_text", "") if doc.exists else ""
