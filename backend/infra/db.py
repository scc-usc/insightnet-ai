"""
db.py — thin shim that re-exports everything from firestore_db so that
existing imports (from infra.db import ...) keep working unchanged.

Supabase + ChromaDB have been replaced by Firestore (see firestore_db.py).
"""

import os
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Environment variables ────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


