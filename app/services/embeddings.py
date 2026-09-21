from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app import db

log = logging.getLogger(__name__)
_lock = threading.Lock()
_model_cache: dict[str, str] = {}


def _headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("llm_api_key"):
        headers["Authorization"] = f"Bearer {settings['llm_api_key']}"
    return headers


def enabled(settings: dict[str, Any]) -> bool:
    return bool(settings.get("llm_enabled") and settings.get("llm_base_url") and settings.get("embeddings_enabled", True))


def resolve_model(settings: dict[str, Any]) -> str | None:
    """Configured embedding model, or the first model on the server whose id mentions 'embed'."""
    configured = (settings.get("embedding_model") or "").strip()
    if configured:
        return configured
    base_url = settings.get("llm_base_url", "").rstrip("/")
    if base_url in _model_cache:
        return _model_cache[base_url]
    try:
        with httpx.Client(timeout=10.0) as client:
            data = client.get(f"{base_url}/models", headers=_headers(settings)).json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        found = next((i for i in ids if "embed" in i.lower()), None)
        if found:
            _model_cache[base_url] = found
        return found
    except Exception as exc:
        log.warning("Could not list models for embeddings: %s", exc)
        return None


def embed_texts(settings: dict[str, Any], texts: list[str]) -> tuple[list[list[float]] | None, str | None]:
    if not enabled(settings) or not texts:
        return None, None
    model = resolve_model(settings)
    if not model:
        return None, None
    base_url = settings["llm_base_url"].rstrip("/")
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=180.0) as client:
            for start in range(0, len(texts), 16):
                batch = [t[:6000] for t in texts[start:start + 16]]
                resp = client.post(f"{base_url}/embeddings", headers=_headers(settings), json={"model": model, "input": batch})
                resp.raise_for_status()
                items = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
                vectors.extend([d["embedding"] for d in items])
    except Exception as exc:
        log.warning("Embedding request failed: %s", exc)
        return None, None
    return vectors, model


def paper_text(paper: dict[str, Any]) -> str:
    return f"{paper.get('title', '')}\n\n{paper.get('abstract', '')}\n\n{paper.get('key_contribution', '') or ''}".strip()


def embed_paper(settings: dict[str, Any], paper: dict[str, Any]) -> tuple[list[float] | None, str | None]:
    vectors, model = embed_texts(settings, [paper_text(paper)])
    return (vectors[0], model) if vectors else (None, None)


def backfill(settings: dict[str, Any], limit: int = 500) -> dict[str, Any]:
    """Embed every stored paper that has no embedding for the current model, then recompute scores."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    try:
        if not enabled(settings):
            return {"status": "disabled", "embedded": 0}
        model = resolve_model(settings)
        if not model:
            return {"status": "no-model", "embedded": 0}
        pending = db.papers_without_embedding(model, limit)
        done = 0
        for start in range(0, len(pending), 16):
            chunk = pending[start:start + 16]
            vectors, used = embed_texts(settings, [paper_text(p) for p in chunk])
            if not vectors:
                break
            for p, vec in zip(chunk, vectors):
                db.set_embedding(p["arxiv_id"], vec, used or model)
                done += 1
        db.recompute_scores(model)
        return {"status": "ok", "embedded": done, "model": model}
    finally:
        _lock.release()
