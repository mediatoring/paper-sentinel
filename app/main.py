from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import db
from app.config import ARXIV_CATEGORIES, SUGGESTED_TAGS
from app.scheduler import reschedule, start as start_scheduler, stop as stop_scheduler
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
    view_mode: str = "cards"
    llm_enabled: bool = True
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_temperature: float = 0.2
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
    if payload.view_mode not in {"cards", "compact"}:
        raise HTTPException(status_code=400, detail="Invalid view_mode")
    saved = db.save_settings(payload.model_dump())
    reschedule()
    return saved


@app.get("/api/papers")
def papers(limit: int = Query(100, ge=1, le=500), saved: bool = False, view: str = "all"):
    if view not in db.VIEWS:
        raise HTTPException(status_code=400, detail=f"view must be one of {', '.join(db.VIEWS)}")
    return db.list_papers(limit, saved_only=saved, view=view)


class ReactionPayload(BaseModel):
    reaction: str | None = None


@app.post("/api/papers/{arxiv_id}/reaction")
def paper_set_reaction(arxiv_id: str, payload: ReactionPayload):
    if payload.reaction is not None and payload.reaction not in db.REACTIONS:
        raise HTTPException(status_code=400, detail="reaction must be like, dislike or null")
    paper = db.set_reaction(arxiv_id, payload.reaction)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


class SavePayload(BaseModel):
    saved: bool = True


@app.post("/api/papers/{arxiv_id}/saved")
def paper_set_saved(arxiv_id: str, payload: SavePayload):
    paper = db.set_saved(arxiv_id, payload.saved)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/status")
def status():
    state = db.get_state()
    state["schedule"] = db.get_settings().get("interval_minutes", 360)
    state["counts"] = db.counts()
    state["saved_count"] = state["counts"]["saved"]
    return state


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
