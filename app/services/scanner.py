from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app import db
from app.services.arxiv import fetch_latest
from app.services.llm import analyze_paper
from app.services.matcher import match_paper
from app.services.notifier import send_notifications

_lock = threading.Lock()


def scan_once() -> dict[str, Any]:
    if not _lock.acquire(blocking=False):
        return {"status": "busy", "new": 0, "matched": 0, "scanned": 0}
    try:
        settings = db.get_settings()
        db.set_state("scan_status", "running")
        papers = fetch_latest(settings["categories"], settings["max_results"])
        matched_count = 0
        new_items: list[dict[str, Any]] = []
        recent = db.recent_context(20)
        for paper in papers:
            is_match, matched_tags = match_paper(paper, settings["tags"], settings["match_mode"])
            if not is_match:
                continue
            matched_count += 1
            if db.paper_exists(paper["arxiv_id"]):
                continue
            paper["matched_tags"] = matched_tags
            analysis = analyze_paper(paper, settings, matched_tags, recent)
            db.insert_paper(paper, analysis)
            stored = {**paper, **analysis}
            new_items.append(stored)
            recent.insert(0, {
                "arxiv_id": paper["arxiv_id"],
                "title": paper["title"],
                "key_contribution": analysis.get("key_contribution", ""),
            })
        send_notifications(settings, new_items)
        now = datetime.now(timezone.utc).isoformat()
        db.set_state("last_scan", now)
        db.set_state("last_scan_new", str(len(new_items)))
        db.set_state("last_scan_matched", str(matched_count))
        db.set_state("last_scan_scanned", str(len(papers)))
        db.set_state("scan_status", "idle")
        return {"status": "ok", "new": len(new_items), "matched": matched_count, "scanned": len(papers)}
    except Exception as exc:
        db.set_state("scan_status", "error")
        db.set_state("last_error", str(exc))
        raise
    finally:
        _lock.release()
