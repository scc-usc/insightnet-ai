"""
Shared OpenAI wrapper — retry on 429, exponential backoff, usage logging.
All agents go through chat() and embed(). No raw openai imports elsewhere.
"""

import json
import time
import logging
import threading
from datetime import datetime, timezone

import httpx as _httpx
from openai import OpenAI

from infra.db import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

# OpenRouter client — used for chat and embeddings
DEFAULT_MODEL = "openai/gpt-4.1-mini"
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    timeout=_httpx.Timeout(90, connect=10),
    max_retries=0,
)
openrouter_client = client  # alias for chat_router

USAGE_LOG_FILE = "usage.jsonl"
_log_lock = threading.Lock()


def _log_usage(agent: str, model: str, prompt_tokens: int, completion_tokens: int):
    entry = {
        "agent": agent,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with _log_lock:
            with open(USAGE_LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def chat(
    agent: str,
    model: str,
    messages: list,
    json_mode: bool = False,
    stream: bool = False,
) -> str:
    """Call OpenAI chat completions with retry on 429."""
    kwargs = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if stream:
        kwargs["stream"] = True

    for attempt in range(3):
        try:
            logger.info(f"[{agent}] {model} attempt {attempt + 1}...")
            resp = client.chat.completions.create(**kwargs)

            if stream:
                return resp  # caller iterates the stream

            usage = resp.usage
            _log_usage(agent, model, usage.prompt_tokens, usage.completion_tokens)
            logger.info(f"[{agent}] done — {usage.prompt_tokens}+{usage.completion_tokens} tok")
            return resp.choices[0].message.content

        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 2 ** (attempt + 1)
                logger.warning(f"[{agent}] 429 — retrying in {wait}s")
                time.sleep(wait)
            else:
                raise


def chat_router(
    agent: str,
    messages: list,
    model: str | None = None,
    json_mode: bool = False,
    stream: bool = False,
) -> str:
    """Call OpenRouter chat completions with user-selected model."""
    model = model or DEFAULT_MODEL
    kwargs = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if stream:
        kwargs["stream"] = True

    for attempt in range(3):
        try:
            logger.info(f"[{agent}] {model} (OpenRouter) attempt {attempt + 1}...")
            resp = openrouter_client.chat.completions.create(**kwargs)

            if stream:
                return resp

            usage = resp.usage
            if usage:
                _log_usage(agent, model, usage.prompt_tokens, usage.completion_tokens)
                logger.info(f"[{agent}] done — {usage.prompt_tokens}+{usage.completion_tokens} tok")
            return resp.choices[0].message.content

        except Exception as e:
            # If json_mode is not supported by this model, retry without it
            if json_mode and ("response_format" in str(e).lower() or "json" in str(e).lower() or "400" in str(e)):
                logger.warning(f"[{agent}] json_mode not supported by {model}, retrying without it")
                kwargs.pop("response_format", None)
                json_mode = False
                continue
            if "429" in str(e) and attempt < 2:
                wait = 2 ** (attempt + 1)
                logger.warning(f"[{agent}] 429 — retrying in {wait}s")
                time.sleep(wait)
            else:
                raise


def list_models() -> list[dict]:
    """Fetch available models from OpenRouter."""
    import httpx as _httpx2
    try:
        resp = _httpx2.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        # Return simplified model list sorted by name
        return [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "pricing": {
                    "prompt": m.get("pricing", {}).get("prompt", "0"),
                    "completion": m.get("pricing", {}).get("completion", "0"),
                },
            }
            for m in models
            if m.get("id")
        ]
    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter models: {e}")
        return []


EMBED_MODEL = "perplexity/pplx-embed-v1-0.6b"
EMBED_DIMENSIONS = 512


def embed(texts: list[str]) -> list[list[float]]:
    """Batch-embed with pplx-embed-v1-0.6b at 512 dims (100 per request, retry on 429)."""
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        for attempt in range(3):
            try:
                resp = client.embeddings.create(
                    model=EMBED_MODEL,
                    input=batch,
                    dimensions=EMBED_DIMENSIONS,
                )
                all_embeddings.extend([item.embedding for item in resp.data])
                break
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Embed 429 — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

    return all_embeddings
