from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import DEFAULT_SETTINGS

DATA_DIR = Path(os.getenv("PAPER_SENTINEL_DATA", "data"))
DB_PATH = DATA_DIR / "paper_sentinel.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT NOT NULL,
                authors TEXT NOT NULL,
                categories TEXT NOT NULL,
                published TEXT,
                updated TEXT,
                abs_url TEXT NOT NULL,
                pdf_url TEXT,
                matched_tags TEXT NOT NULL,
                summary TEXT,
                why_relevant TEXT,
                key_contribution TEXT,
                limitations TEXT,
                related_to TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        existing = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (id, payload, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_SETTINGS), _now()),
            )


def get_settings() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
    if not row:
        return dict(DEFAULT_SETTINGS)
    loaded = json.loads(row["payload"])
    return {**DEFAULT_SETTINGS, **loaded}


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_SETTINGS, **settings}
    merged["interval_minutes"] = max(30, int(merged["interval_minutes"]))
    merged["max_results"] = min(300, max(10, int(merged["max_results"])))
    with connect() as conn:
        conn.execute(
            "UPDATE settings SET payload = ?, updated_at = ? WHERE id = 1",
            (json.dumps(merged), _now()),
        )
    return merged


def paper_exists(arxiv_id: str) -> bool:
    with connect() as conn:
        return bool(conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone())


def insert_paper(paper: dict[str, Any], analysis: dict[str, str]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO papers (
                arxiv_id, title, abstract, authors, categories, published, updated,
                abs_url, pdf_url, matched_tags, summary, why_relevant,
                key_contribution, limitations, related_to, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper["arxiv_id"], paper["title"], paper["abstract"],
                json.dumps(paper["authors"]), json.dumps(paper["categories"]),
                paper.get("published"), paper.get("updated"), paper["abs_url"],
                paper.get("pdf_url"), json.dumps(paper.get("matched_tags", [])),
                analysis.get("summary", ""), analysis.get("why_relevant", ""),
                analysis.get("key_contribution", ""), analysis.get("limitations", ""),
                analysis.get("related_to", ""), _now(),
            ),
        )


def _paper_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("authors", "categories", "matched_tags"):
        d[key] = json.loads(d[key] or "[]")
    return d


def list_papers(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM papers ORDER BY COALESCE(published, created_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_paper_row_to_dict(r) for r in rows]


def recent_context(limit: int = 20) -> list[dict[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT arxiv_id, title, key_contribution FROM papers ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_state(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_state() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM state").fetchall()
    return {r["key"]: r["value"] for r in rows}
