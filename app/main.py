from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import db
from app.config import ARXIV_CATEGORIES, LEGACY_VIEW_MODES, SUGGESTED_TAGS, VIEW_MODES
from app.scheduler import reschedule, start as start_scheduler, stop as stop_scheduler
from app.services import embeddings, library, llm_health
from app.services.scanner import scan_once

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Paper Sentinel", version="0.1.0", lifespan=lifespan)
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _asset_version() -> str:
    """Changes whenever a static file changes, so browsers never serve a stale app.js/styles.css."""
    return str(int(max(f.stat().st_mtime for f in STATIC_DIR.iterdir() if f.is_file())))


@app.middleware("http")
async def static_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


class SettingsPayload(BaseModel):
    categories: list[str]
    tags: list[str]
    match_mode: str = "any"
    interval_minutes: int = 360
    max_results: int = 100
    summary_length: str = "medium"
    view_mode: str = "cards3"
    llm_enabled: bool = True
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    embeddings_enabled: bool = True
    embedding_model: str = ""
    library_auto_download: bool = True
    browser_notifications: bool = True
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_starttls: bool = True
    webhook_enabled: bool = False
    webhook_url: str = ""


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": ARXIV_CATEGORIES,
            "suggested_tags": SUGGESTED_TAGS,
            "asset_version": _asset_version(),
        },
    )


@app.get("/api/settings")
def settings_get():
    return db.get_settings()


@app.post("/api/settings")
def settings_save(payload: SettingsPayload):
    allowed_categories = {c[0] for c in ARXIV_CATEGORIES}
    categories = [c for c in payload.categories if c in allowed_categories]
    if not categories:
        raise HTTPException(status_code=400, detail="Select at least one arXiv category.")
    if payload.match_mode not in {"any", "all"}:
        raise HTTPException(status_code=400, detail="match_mode must be any or all")
    if payload.summary_length not in {"short", "medium", "long"}:
        raise HTTPException(status_code=400, detail="Invalid summary_length")
    if payload.view_mode not in VIEW_MODES and payload.view_mode not in LEGACY_VIEW_MODES:
        raise HTTPException(status_code=400, detail=f"view_mode must be one of {', '.join(VIEW_MODES)}")
    saved = db.save_settings(payload.model_dump())
    reschedule()
    return saved


class ViewModePayload(BaseModel):
    view_mode: str


@app.post("/api/settings/view-mode")
def settings_view_mode(payload: ViewModePayload):
    """Quick switch used by the toolbar; keeps the rest of the settings untouched."""
    if payload.view_mode not in VIEW_MODES:
        raise HTTPException(status_code=400, detail=f"view_mode must be one of {', '.join(VIEW_MODES)}")
    settings = db.get_settings()
    settings["view_mode"] = payload.view_mode
    return db.save_settings(settings)


@app.get("/api/papers")
def papers(limit: int = Query(100, ge=1, le=500), saved: bool = False, view: str = "all", sort: str = "newest"):
    if view not in db.VIEWS:
        raise HTTPException(status_code=400, detail=f"view must be one of {', '.join(db.VIEWS)}")
    if sort not in db.SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(db.SORTS)}")
    return db.list_papers(limit, saved_only=saved, view=view, sort=sort)


# ---------------------------------------------------------------------------
# Search: full-text (FTS5), semantic (embeddings) or hybrid (reciprocal rank fusion)
# ---------------------------------------------------------------------------

SEARCH_MODES = ("text", "semantic", "hybrid")


def _rrf(*lists: list[dict], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    for results in lists:
        for rank, item in enumerate(results):
            arxiv_id = item["arxiv_id"]
            scores[arxiv_id] = scores.get(arxiv_id, 0.0) + 1.0 / (k + rank + 1)
            merged = items.setdefault(arxiv_id, {})
            merged.update({key: val for key, val in item.items() if key not in merged or val is not None})
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for arxiv_id, score in ordered:
        d = items[arxiv_id]
        d["fusion_score"] = round(score, 5)
        out.append(d)
    return out


@app.get("/api/search")
def search(q: str = Query("", max_length=500), mode: str = "hybrid", view: str = "all", limit: int = Query(50, ge=1, le=200)):
    q = q.strip()
    if not q:
        return {"query": q, "mode": mode, "results": [], "semantic_available": False}
    if mode not in SEARCH_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {', '.join(SEARCH_MODES)}")
    if view not in db.VIEWS:
        raise HTTPException(status_code=400, detail=f"view must be one of {', '.join(db.VIEWS)}")
    settings = db.get_settings()
    text_results = db.search_text(q, limit, view) if mode in ("text", "hybrid") else []
    semantic_results: list[dict] = []
    semantic_available = False
    if mode in ("semantic", "hybrid"):
        vectors, model = embeddings.embed_texts(settings, [q])
        if vectors:
            semantic_available = True
            semantic_results = db.rank_by_vector(vectors[0], limit, model=model, view=view)
    if mode == "text":
        results = text_results
    elif mode == "semantic":
        results = semantic_results
    else:
        results = _rrf(text_results, semantic_results)[:limit] if semantic_results else text_results
    return {"query": q, "mode": mode, "results": results, "semantic_available": semantic_available}


@app.get("/api/papers/{arxiv_id}/similar")
def paper_similar(arxiv_id: str, limit: int = Query(6, ge=1, le=30)):
    vec, model = db.get_embedding(arxiv_id)
    if vec is None:
        paper = db.get_paper(arxiv_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        vec, model = embeddings.embed_paper(db.get_settings(), paper)
        if vec is None:
            raise HTTPException(status_code=503, detail="Embeddings are not available. Check the local LLM server and embedding model in Settings.")
        db.set_embedding(arxiv_id, vec, model or "")
    return {"arxiv_id": arxiv_id, "results": db.rank_by_vector(vec, limit, exclude=arxiv_id, model=model)}


@app.post("/api/embeddings/rebuild")
def embeddings_rebuild(background_tasks: BackgroundTasks):
    settings = db.get_settings()
    if not embeddings.enabled(settings):
        raise HTTPException(status_code=400, detail="Embeddings are disabled or the LLM server is not configured.")
    background_tasks.add_task(embeddings.backfill, settings)
    return {"status": "started"}


# ---------------------------------------------------------------------------
# Notes and user tags
# ---------------------------------------------------------------------------

class NotesPayload(BaseModel):
    notes: str = ""
    user_tags: list[str] = []


@app.post("/api/papers/{arxiv_id}/notes")
def paper_set_notes(arxiv_id: str, payload: NotesPayload):
    paper = db.set_notes(arxiv_id, payload.notes[:20000], payload.user_tags[:50])
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/tags")
def user_tags():
    return {"tags": db.all_user_tags()}


# ---------------------------------------------------------------------------
# PDF library
# ---------------------------------------------------------------------------

@app.post("/api/papers/{arxiv_id}/pdf")
def paper_download_pdf(arxiv_id: str):
    try:
        return library.download_pdf(arxiv_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Paper not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}")


@app.delete("/api/papers/{arxiv_id}/pdf")
def paper_remove_pdf(arxiv_id: str):
    paper = library.remove_pdf(arxiv_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/library/{arxiv_id}.pdf")
def library_pdf(arxiv_id: str):
    file = library.pdf_file(arxiv_id)
    if file is None:
        raise HTTPException(status_code=404, detail="PDF not in library")
    return FileResponse(file, media_type="application/pdf", filename=file.name)


def _auto_download(arxiv_id: str) -> None:
    try:
        library.download_pdf(arxiv_id)
    except Exception as exc:  # background task: never crash the request
        import logging
        logging.getLogger(__name__).warning("Auto PDF download failed for %s: %s", arxiv_id, exc)


class ReactionPayload(BaseModel):
    reaction: str | None = None


@app.post("/api/papers/{arxiv_id}/reaction")
def paper_set_reaction(arxiv_id: str, payload: ReactionPayload, background_tasks: BackgroundTasks):
    if payload.reaction is not None and payload.reaction not in db.REACTIONS:
        raise HTTPException(status_code=400, detail="reaction must be like, dislike or null")
    paper = db.set_reaction(arxiv_id, payload.reaction)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    settings = db.get_settings()
    background_tasks.add_task(db.recompute_scores, embeddings.resolve_model(settings) if embeddings.enabled(settings) else None)
    if payload.reaction == "like" and settings.get("library_auto_download") and not paper.get("has_pdf"):
        background_tasks.add_task(_auto_download, arxiv_id)
    return paper


class SavePayload(BaseModel):
    saved: bool = True


@app.post("/api/papers/{arxiv_id}/saved")
def paper_set_saved(arxiv_id: str, payload: SavePayload, background_tasks: BackgroundTasks):
    paper = db.set_saved(arxiv_id, payload.saved)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    if payload.saved and db.get_settings().get("library_auto_download") and not paper.get("has_pdf"):
        background_tasks.add_task(_auto_download, arxiv_id)
    return paper


@app.get("/api/status")
def status():
    state = db.get_state()
    state["schedule"] = db.get_settings().get("interval_minutes", 360)
    state["counts"] = db.counts()
    state["saved_count"] = state["counts"]["saved"]
    state["library"] = db.embedding_stats()
    state["llm"] = llm_health.probe(db.get_settings())
    return state


# ---------------------------------------------------------------------------
# LLM server monitor
# ---------------------------------------------------------------------------

@app.get("/api/llm/health")
def llm_health_get(force: bool = False):
    return llm_health.probe(db.get_settings(), force=force)


@app.post("/api/llm/start")
def llm_start(background_tasks: BackgroundTasks):
    settings = db.get_settings()
    state = llm_health.probe(settings, force=True)
    if state["reachable"]:
        return {"ok": True, "detail": "Server is already running."}
    if not state["can_start"]:
        raise HTTPException(status_code=400, detail=f"No local CLI found. Start it manually: {state['hints']['start']}")
    background_tasks.add_task(llm_health.start_server, settings)
    return {"ok": True, "detail": "Starting in the background…"}


class LoadPayload(BaseModel):
    kind: str = "chat"


@app.post("/api/llm/load")
def llm_load(payload: LoadPayload, background_tasks: BackgroundTasks):
    if payload.kind not in ("chat", "embedding"):
        raise HTTPException(status_code=400, detail="kind must be chat or embedding")
    settings = db.get_settings()
    state = llm_health.probe(settings, force=True)
    if not state["reachable"]:
        raise HTTPException(status_code=409, detail="Server is not reachable; start it first.")
    if not state["can_start"]:
        key = "load_chat" if payload.kind == "chat" else "load_embedding"
        raise HTTPException(status_code=400, detail=f"No local CLI found. Load it manually: {state['hints'][key]}")
    background_tasks.add_task(llm_health.load_model, settings, payload.kind)
    return {"ok": True, "detail": "Loading in the background…"}


@app.post("/api/scan")
def scan(background_tasks: BackgroundTasks):
    if db.get_state().get("scan_status") == "running":
        return {"status": "busy"}
    background_tasks.add_task(scan_once)
    return {"status": "started"}


@app.get("/feed.xml")
def feed():
    papers = db.list_papers(50)
    items = []
    for p in papers:
        description = escape(p.get("summary") or p.get("abstract", ""))
        items.append(
            f"<item><title>{escape(p['title'])}</title>"
            f"<link>{escape(p['abs_url'])}</link>"
            f"<guid>{escape(p['arxiv_id'])}</guid>"
            f"<description>{description}</description></item>"
        )
    body = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<rss version=\"2.0\"><channel><title>Paper Sentinel</title>"
        "<link>http://localhost:5792/</link>"
        "<description>Local AI-curated arXiv research radar</description>"
        + "".join(items) + "</channel></rss>"
    )
    return Response(body, media_type="application/rss+xml")
