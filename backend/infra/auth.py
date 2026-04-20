"""
FastAPI dependencies for Firebase Auth token verification and rate limiting.

Usage in route:
    from infra.auth import require_user, require_admin

    @app.post("/query")
    async def query_endpoint(req: QueryRequest, uid: str = Depends(require_user)):
        ...

    @app.post("/ingest")
    async def ingest_endpoint(req: IngestRequest, uid: str = Depends(require_admin)):
        ...
"""

import os
import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth as firebase_auth

from infra.firestore_db import get_db, check_rate_limit

logger = logging.getLogger(__name__)

# Admin UIDs — comma-separated list in env var ADMIN_UIDS
# e.g. ADMIN_UIDS="uid1,uid2"
_ADMIN_UIDS: set[str] = set(
    uid.strip()
    for uid in os.getenv("ADMIN_UIDS", "").split(",")
    if uid.strip()
)

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=512)
def _cached_verify(token: str) -> str:
    """
    Verify a Firebase ID token and return the uid.
    LRU-cached: tokens are valid for 1 hour, cache avoids repeated RTTs.
    Not suitable for revocation checks — acceptable for this use case.
    """
    get_db()  # ensure Firebase app is initialized before verifying tokens
    decoded = firebase_auth.verify_id_token(token)
    return decoded["uid"]


async def require_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    FastAPI dependency — verifies Firebase ID token.
    Returns the caller's uid on success, raises 401 otherwise.
    Also enforces per-user rate limits; raises 429 if exceeded.
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header (Bearer <firebase-id-token>)",
        )

    try:
        uid = _cached_verify(creds.credentials)
    except firebase_admin.exceptions.FirebaseError as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not check_rate_limit(uid):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before sending another request.",
        )

    return uid


async def require_admin(
    uid: str = Depends(require_user),
) -> str:
    """
    FastAPI dependency — requires the caller to be in ADMIN_UIDS.
    Use for sensitive endpoints like /ingest.
    """
    if _ADMIN_UIDS and uid not in _ADMIN_UIDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return uid
