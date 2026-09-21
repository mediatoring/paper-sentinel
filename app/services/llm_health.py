from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services import embeddings

log = logging.getLogger(__name__)

CACHE_SECONDS = 8.0
_cache: dict[str, Any] = {"at": 0.0, "key": None, "value": None}
_lock = threading.Lock()
_actions: dict[str, Any] = {"status": "idle", "action": None, "detail": "", "at": None}


# ---------------------------------------------------------------------------
# Provider detection and CLI hints
# ---------------------------------------------------------------------------

def provider_for(base_url: str) -> str:
    url = urlparse(base_url or "")
    host = (url.hostname or "").lower()
    if url.port == 11434 or "ollama" in host:
        return "ollama"
    if url.port == 1234 or "lmstudio" in host:
        return "lmstudio"
    return "generic"


def _lms_path() -> str | None:
    found = shutil.which("lms")
    if found:
        return found
    candidate = Path.home() / ".lmstudio" / "bin" / "lms"
    return str(candidate) if candidate.exists() and os.access(candidate, os.X_OK) else None


def _ollama_path() -> str | None:
    return shutil.which("ollama")


def cli_for(provider: str) -> str | None:
    if provider == "lmstudio":
        return _lms_path()
    if provider == "ollama":
        return _ollama_path()
    return None


def hints(provider: str, base_url: str, chat_model: str, embedding_model: str | None) -> dict[str, str]:
    port = urlparse(base_url).port or (1234 if provider == "lmstudio" else 11434)
    if provider == "lmstudio":
        return {
            "name": "LM Studio",
            "install": "Download LM Studio from https://lmstudio.ai and enable the CLI with: lms bootstrap",
            "start": f"lms server start --port {port}",
            "load_chat": f"lms load {chat_model} -y" if chat_model else "lms load <model> -y",
            "load_embedding": f"lms load {embedding_model} -y" if embedding_model else "lms load text-embedding-nomic-embed-text-v1.5 -y",
            "gui": "Or open LM Studio → Developer tab → Start Server, then load a model.",
        }
    if provider == "ollama":
        return {
            "name": "Ollama",
            "install": "Install Ollama from https://ollama.com",
            "start": "ollama serve",
            "load_chat": f"ollama pull {chat_model}" if chat_model else "ollama pull llama3.1",
            "load_embedding": f"ollama pull {embedding_model}" if embedding_model else "ollama pull nomic-embed-text",
            "gui": "Ollama usually runs as a background service after installation.",
        }
    return {
        "name": "OpenAI-compatible server",
        "install": "",
        "start": f"Start your server so that {base_url}/models responds.",
        "load_chat": "",
        "load_embedding": "",
        "gui": "",
    }


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def _headers(settings: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings['llm_api_key']}"} if settings.get("llm_api_key") else {}


def _lmstudio_states(base_url: str, headers: dict[str, str]) -> dict[str, str] | None:
    """LM Studio's native API tells which models are actually loaded (the OpenAI list does not)."""
    root = base_url[:-3] if base_url.endswith("/v1") else base_url
    try:
        with httpx.Client(timeout=3.0) as client:
            data = client.get(f"{root}/api/v0/models", headers=headers).json()
        return {m.get("id", ""): m.get("state", "") for m in data.get("data", [])}
    except Exception:
        return None


def probe(settings: dict[str, Any], force: bool = False) -> dict[str, Any]:
    base_url = (settings.get("llm_base_url") or "").rstrip("/")
    chat_model = settings.get("llm_model") or ""
    key = (base_url, chat_model, settings.get("embedding_model"), bool(settings.get("llm_enabled")))
    now = time.monotonic()
    with _lock:
        if not force and _cache["key"] == key and now - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    result = _probe(settings, base_url, chat_model)
    with _lock:
        _cache.update({"at": time.monotonic(), "key": key, "value": result})
    return result


def _probe(settings: dict[str, Any], base_url: str, chat_model: str) -> dict[str, Any]:
    provider = provider_for(base_url)
    embedding_model = (settings.get("embedding_model") or "").strip() or None
    result: dict[str, Any] = {
        "enabled": bool(settings.get("llm_enabled")),
        "base_url": base_url,
        "provider": provider,
        "reachable": False,
        "latency_ms": None,
        "models": [],
        "chat_model": chat_model,
        "chat_loaded": None,
        "embedding_model": embedding_model,
        "embedding_loaded": None,
        "embeddings_enabled": settings.get("embeddings_enabled", True),
        "error": "",
        "can_start": cli_for(provider) is not None,
        "action": dict(_actions),
    }
    if not base_url:
        result["error"] = "No LLM base URL configured."
        result["hints"] = hints(provider, base_url, chat_model, embedding_model)
        return result
    headers = _headers(settings)
    started = time.monotonic()
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{base_url}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        result["reachable"] = True
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        result["models"] = ids
    except httpx.ConnectError:
        result["error"] = f"Nothing is listening at {base_url}."
    except httpx.TimeoutException:
        result["error"] = f"{base_url} did not answer within 3 s."
    except httpx.HTTPStatusError as exc:
        result["error"] = f"{base_url}/models answered {exc.response.status_code}."
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"

    if result["reachable"]:
        if not embedding_model:
            embedding_model = next((i for i in result["models"] if "embed" in i.lower()), None)
            result["embedding_model"] = embedding_model
        states = _lmstudio_states(base_url, headers) if provider == "lmstudio" else None
        if states is not None:
            result["chat_loaded"] = states.get(chat_model) == "loaded" if chat_model in states else None
            result["embedding_loaded"] = states.get(embedding_model) == "loaded" if embedding_model in states else None
            result["chat_available"] = chat_model in states
            result["embedding_available"] = embedding_model in states if embedding_model else False
            result["loaded_models"] = [m for m, s in states.items() if s == "loaded"]
        else:
            result["chat_available"] = chat_model in result["models"] if result["models"] else None
            result["embedding_available"] = (embedding_model in result["models"]) if (embedding_model and result["models"]) else None
    result["hints"] = hints(provider, base_url, chat_model, embedding_model)
    return result


# ---------------------------------------------------------------------------
# Actions: start the server / load a model (only when Paper Sentinel runs on the same machine)
# ---------------------------------------------------------------------------

def _set_action(status: str, action: str | None, detail: str = "") -> None:
    with _lock:
        _actions.update({"status": status, "action": action, "detail": detail, "at": time.time()})


def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out[-2000:]


def _wait_reachable(settings: dict[str, Any], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if probe(settings, force=True)["reachable"]:
            return True
        time.sleep(1.0)
    return False


def start_server(settings: dict[str, Any]) -> dict[str, Any]:
    base_url = (settings.get("llm_base_url") or "").rstrip("/")
    provider = provider_for(base_url)
    cli = cli_for(provider)
    if not cli:
        return {"ok": False, "detail": f"No local CLI found for {provider}. Start the server manually: {hints(provider, base_url, '', None)['start']}"}
    _set_action("running", "start", "Starting server…")
    try:
        if provider == "lmstudio":
            port = urlparse(base_url).port or 1234
            code, out = _run([cli, "server", "start", "--port", str(port)], timeout=60)
            if code != 0:
                _set_action("error", "start", out)
                return {"ok": False, "detail": out or "lms server start failed"}
        else:  # ollama: serve is a long-running process
            subprocess.Popen([cli, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        ok = _wait_reachable(settings, 20)
        _set_action("idle" if ok else "error", "start", "Server started." if ok else "Started the command but the server is still not reachable.")
        return {"ok": ok, "detail": _actions["detail"]}
    except Exception as exc:
        _set_action("error", "start", str(exc))
        return {"ok": False, "detail": str(exc)}


def load_model(settings: dict[str, Any], kind: str) -> dict[str, Any]:
    base_url = (settings.get("llm_base_url") or "").rstrip("/")
    provider = provider_for(base_url)
    cli = cli_for(provider)
    state = probe(settings, force=True)
    model = state["chat_model"] if kind == "chat" else state.get("embedding_model")
    if not model:
        return {"ok": False, "detail": "No model configured."}
    if not cli:
        return {"ok": False, "detail": f"No local CLI found. Load it manually: {state['hints']['load_chat' if kind == 'chat' else 'load_embedding']}"}
    _set_action("running", f"load_{kind}", f"Loading {model}…")
    try:
        if provider == "lmstudio":
            code, out = _run([cli, "load", model, "-y", "--identifier", model], timeout=600)
        else:
            code, out = _run([cli, "pull", model], timeout=1800)
        ok = code == 0
        _set_action("idle" if ok else "error", f"load_{kind}", f"{model} loaded." if ok else out)
        probe(settings, force=True)
        return {"ok": ok, "detail": _actions["detail"]}
    except Exception as exc:
        _set_action("error", f"load_{kind}", str(exc))
        return {"ok": False, "detail": str(exc)}
