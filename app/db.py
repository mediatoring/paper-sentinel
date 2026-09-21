from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from array import array
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import DEFAULT_SETTINGS, normalize_view_mode

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
                created_at TEXT NOT NULL,
                saved INTEGER NOT NULL DEFAULT 0,
                saved_at TEXT,
                reaction TEXT,
                reacted_at TEXT,
                notes TEXT NOT NULL DEFAULT '',
                user_tags TEXT NOT NULL DEFAULT '[]',
                pdf_path TEXT,
                pdf_size INTEGER,
                pdf_text TEXT,
                pdf_fetched_at TEXT,
                embedding BLOB,
                embedding_model TEXT,
                score REAL,
                read_at TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                arxiv_id UNINDEXED, title, abstract, summary, notes, user_tags, fulltext,
                tokenize = 'porter unicode61'
            );

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        _migrate(conn)
        existing = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (id, payload, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_SETTINGS), _now()),
            )


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
    if "saved" not in columns:
        conn.execute("ALTER TABLE papers ADD COLUMN saved INTEGER NOT NULL DEFAULT 0")
    if "saved_at" not in columns:
        conn.execute("ALTER TABLE papers ADD COLUMN saved_at TEXT")
    if "reaction" not in columns:
        conn.execute("ALTER TABLE papers ADD COLUMN reaction TEXT")
    if "reacted_at" not in columns:
        conn.execute("ALTER TABLE papers ADD COLUMN reacted_at TEXT")
    for name, decl in (
        ("notes", "TEXT NOT NULL DEFAULT ''"),
        ("user_tags", "TEXT NOT NULL DEFAULT '[]'"),
        ("pdf_path", "TEXT"),
        ("pdf_size", "INTEGER"),
        ("pdf_text", "TEXT"),
        ("pdf_fetched_at", "TEXT"),
        ("embedding", "BLOB"),
        ("embedding_model", "TEXT"),
        ("score", "REAL"),
        ("read_at", "TEXT"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {decl}")
    # Backfill the full-text index for databases created before it existed.
    if conn.execute("SELECT COUNT(*) FROM papers_fts").fetchone()[0] == 0:
        for row in conn.execute("SELECT arxiv_id FROM papers").fetchall():
            _reindex(conn, row["arxiv_id"])


def _reindex(conn: sqlite3.Connection, arxiv_id: str) -> None:
    conn.execute("DELETE FROM papers_fts WHERE arxiv_id = ?", (arxiv_id,))
    row = conn.execute(
        "SELECT arxiv_id, title, abstract, summary, notes, user_tags, pdf_text FROM papers WHERE arxiv_id = ?",
        (arxiv_id,),
    ).fetchone()
    if row is None:
        return
    tags = " ".join(json.loads(row["user_tags"] or "[]"))
    conn.execute(
        "INSERT INTO papers_fts (arxiv_id, title, abstract, summary, notes, user_tags, fulltext) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row["arxiv_id"], row["title"], row["abstract"], row["summary"] or "", row["notes"] or "", tags, row["pdf_text"] or ""),
    )


def get_settings() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
    if not row:
        return dict(DEFAULT_SETTINGS)
    loaded = json.loads(row["payload"])
    merged = {**DEFAULT_SETTINGS, **loaded}
    merged["view_mode"] = normalize_view_mode(merged.get("view_mode"))
    return merged


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_SETTINGS, **settings}
    merged["interval_minutes"] = max(30, int(merged["interval_minutes"]))
    merged["max_results"] = min(300, max(10, int(merged["max_results"])))
    merged["view_mode"] = normalize_view_mode(merged.get("view_mode"))
    with connect() as conn:
        conn.execute(
            "UPDATE settings SET payload = ?, updated_at = ? WHERE id = 1",
            (json.dumps(merged), _now()),
        )
    return merged


def paper_exists(arxiv_id: str) -> bool:
    with connect() as conn:
        return bool(conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone())


def insert_paper(
    paper: dict[str, Any],
    analysis: dict[str, str],
    embedding: list[float] | None = None,
    embedding_model: str | None = None,
    score: float | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO papers (
                arxiv_id, title, abstract, authors, categories, published, updated,
                abs_url, pdf_url, matched_tags, summary, why_relevant,
                key_contribution, limitations, related_to, created_at,
                embedding, embedding_model, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper["arxiv_id"], paper["title"], paper["abstract"],
                json.dumps(paper["authors"]), json.dumps(paper["categories"]),
                paper.get("published"), paper.get("updated"), paper["abs_url"],
                paper.get("pdf_url"), json.dumps(paper.get("matched_tags", [])),
                analysis.get("summary", ""), analysis.get("why_relevant", ""),
                analysis.get("key_contribution", ""), analysis.get("limitations", ""),
                analysis.get("related_to", ""), _now(),
                _pack(embedding) if embedding else None, embedding_model if embedding else None, score,
            ),
        )
        _reindex(conn, paper["arxiv_id"])


def _paper_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("authors", "categories", "matched_tags", "user_tags"):
        d[key] = json.loads(d[key] or "[]")
    d["saved"] = bool(d.get("saved"))
    d["has_embedding"] = d.get("embedding") is not None
    d["has_pdf"] = bool(d.get("pdf_path"))
    d["has_fulltext"] = bool(d.get("pdf_text"))
    d.pop("embedding", None)
    d.pop("pdf_text", None)
    return d


PAPER_COLUMNS = "papers.*"


def get_paper(arxiv_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row) if row else None


REACTIONS = ("like", "dislike")
VIEWS = {
    "inbox": ("WHERE reaction IS NULL AND saved = 0 AND read_at IS NULL", "COALESCE(published, created_at) DESC"),
    "all": ("", "COALESCE(published, created_at) DESC"),
    "saved": ("WHERE saved = 1", "saved_at DESC"),
    "liked": ("WHERE reaction = 'like'", "reacted_at DESC"),
    "disliked": ("WHERE reaction = 'dislike'", "reacted_at DESC"),
}


SORTS = {"newest": None, "score": "score DESC NULLS LAST, COALESCE(published, created_at) DESC"}


def _filters(view: str, tags: list[str] | None) -> tuple[list[str], list[Any]]:
    """SQL clauses (without WHERE/AND) and params for a view plus an optional any-of tag filter."""
    clauses: list[str] = []
    params: list[Any] = []
    where, _ = VIEWS.get(view, VIEWS["all"])
    if where:
        clauses.append(where.replace("WHERE ", ""))
    wanted = [t.strip().lower() for t in (tags or []) if t and t.strip()]
    if wanted:
        marks = ",".join("?" * len(wanted))
        clauses.append(
            f"(EXISTS (SELECT 1 FROM json_each(papers.matched_tags) WHERE lower(value) IN ({marks}))"
            f" OR EXISTS (SELECT 1 FROM json_each(papers.user_tags) WHERE lower(value) IN ({marks})))"
        )
        params.extend(wanted)
        params.extend(wanted)
    return clauses, params


def list_papers(limit: int = 100, saved_only: bool = False, view: str = "all", sort: str = "newest",
                tags: list[str] | None = None) -> list[dict[str, Any]]:
    if saved_only:
        view = "saved"
    _, order = VIEWS.get(view, VIEWS["all"])
    if SORTS.get(sort):
        order = SORTS[sort]
    clauses, params = _filters(view, tags)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM papers {where} ORDER BY {order} LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [_paper_row_to_dict(r) for r in rows]


def tag_counts(view: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Tags in use with paper counts, split into radar (matched) tags and your own tags."""
    clauses, params = _filters(view, None)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    out: dict[str, list[dict[str, Any]]] = {}
    with connect() as conn:
        for key, column in (("matched", "matched_tags"), ("user", "user_tags")):
            rows = conn.execute(
                f"""
                SELECT MIN(value) AS tag, COUNT(DISTINCT papers.arxiv_id) AS n
                FROM papers, json_each(papers.{column}) {where}
                GROUP BY lower(value) ORDER BY n DESC, lower(value)
                """,
                params,
            ).fetchall()
            out[key] = [{"tag": r["tag"], "count": int(r["n"])} for r in rows]
    return out


def set_reaction(arxiv_id: str, reaction: str | None) -> dict[str, Any] | None:
    if reaction not in REACTIONS and reaction is not None:
        raise ValueError(f"reaction must be one of {REACTIONS} or null")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE papers SET reaction = ?, reacted_at = ? WHERE arxiv_id = ?",
            (reaction, _now() if reaction else None, arxiv_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row)


def counts() -> dict[str, int]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(saved = 1) AS saved,
                   SUM(reaction = 'like') AS liked,
                   SUM(reaction = 'dislike') AS disliked,
                   SUM(reaction IS NULL AND saved = 0 AND read_at IS NULL) AS inbox,
                   SUM(read_at IS NOT NULL) AS read
            FROM papers
            """
        ).fetchone()
    return {k: int(row[k] or 0) for k in ("total", "saved", "liked", "disliked", "inbox", "read")}


def set_saved(arxiv_id: str, saved: bool) -> dict[str, Any] | None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE papers SET saved = ?, saved_at = ? WHERE arxiv_id = ?",
            (1 if saved else 0, _now() if saved else None, arxiv_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row)


def count_saved() -> int:
    return counts()["saved"]


def set_read(arxiv_id: str, read: bool) -> dict[str, Any] | None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE papers SET read_at = ? WHERE arxiv_id = ?",
            (_now() if read else None, arxiv_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row)


def mark_all_read(tags: list[str] | None = None) -> int:
    """Mark every paper currently in the inbox (optionally only those with given tags) as read."""
    clauses, params = _filters("inbox", tags)
    with connect() as conn:
        cur = conn.execute(f"UPDATE papers SET read_at = ? WHERE {' AND '.join(clauses)}", (_now(), *params))
        return cur.rowcount


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


# ---------------------------------------------------------------------------
# Notes and user tags
# ---------------------------------------------------------------------------

def set_notes(arxiv_id: str, notes: str, user_tags: list[str]) -> dict[str, Any] | None:
    clean_tags: list[str] = []
    for tag in user_tags:
        t = re.sub(r"\s+", " ", str(tag)).strip()
        if t and t.lower() not in {c.lower() for c in clean_tags}:
            clean_tags.append(t[:60])
    with connect() as conn:
        cur = conn.execute(
            "UPDATE papers SET notes = ?, user_tags = ? WHERE arxiv_id = ?",
            (notes.strip(), json.dumps(clean_tags), arxiv_id),
        )
        if cur.rowcount == 0:
            return None
        _reindex(conn, arxiv_id)
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row)


def all_user_tags() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT user_tags FROM papers WHERE user_tags != '[]'").fetchall()
    seen: dict[str, str] = {}
    for r in rows:
        for t in json.loads(r["user_tags"] or "[]"):
            seen.setdefault(t.lower(), t)
    return sorted(seen.values(), key=str.lower)


# ---------------------------------------------------------------------------
# PDF library
# ---------------------------------------------------------------------------

def set_pdf(arxiv_id: str, path: str | None, size: int | None, text: str | None) -> dict[str, Any] | None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE papers SET pdf_path = ?, pdf_size = ?, pdf_text = ?, pdf_fetched_at = ? WHERE arxiv_id = ?",
            (path, size, text, _now() if path else None, arxiv_id),
        )
        if cur.rowcount == 0:
            return None
        _reindex(conn, arxiv_id)
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return _paper_row_to_dict(row)


def get_pdf_path(arxiv_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT pdf_path FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return row["pdf_path"] if row else None


# ---------------------------------------------------------------------------
# Full-text search (SQLite FTS5, Porter stemming)
# ---------------------------------------------------------------------------

def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: quoted phrases kept, words prefix-matched, AND-ed."""
    parts: list[str] = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', text):
        if phrase:
            parts.append('"' + phrase.replace('"', " ") + '"')
        else:
            w = re.sub(r"[^\w\-]", "", word, flags=re.UNICODE)
            if w:
                parts.append('"' + w + '"*')
    return " AND ".join(parts)


def search_text(query: str, limit: int = 50, view: str = "all", tags: list[str] | None = None) -> list[dict[str, Any]]:
    q = fts_query(query)
    if not q:
        return []
    clauses, params = _filters(view, tags)
    extra = "".join(f" AND {c}" for c in clauses)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT papers.*, bm25(papers_fts, 8.0, 3.0, 2.0, 4.0, 5.0, 1.0) AS rank,
                   snippet(papers_fts, -1, '<mark>', '</mark>', ' … ', 18) AS snippet
            FROM papers_fts JOIN papers ON papers.arxiv_id = papers_fts.arxiv_id
            WHERE papers_fts MATCH ? {extra}
            ORDER BY rank LIMIT ?
            """,
            (q, *params, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = _paper_row_to_dict(r)
        d["text_rank"] = float(r["rank"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Embeddings, similarity and preference score
# ---------------------------------------------------------------------------

def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def set_embedding(arxiv_id: str, vec: list[float], model: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE papers SET embedding = ?, embedding_model = ? WHERE arxiv_id = ?",
            (_pack(vec), model, arxiv_id),
        )


def papers_without_embedding(model: str, limit: int = 500) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT arxiv_id, title, abstract, key_contribution FROM papers "
            "WHERE embedding IS NULL OR embedding_model IS NOT ? ORDER BY created_at DESC LIMIT ?",
            (model, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def all_embeddings(model: str | None = None) -> list[tuple[str, list[float]]]:
    with connect() as conn:
        if model:
            rows = conn.execute(
                "SELECT arxiv_id, embedding FROM papers WHERE embedding IS NOT NULL AND embedding_model = ?", (model,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT arxiv_id, embedding FROM papers WHERE embedding IS NOT NULL").fetchall()
    return [(r["arxiv_id"], _unpack(r["embedding"])) for r in rows]


def get_embedding(arxiv_id: str) -> tuple[list[float] | None, str | None]:
    with connect() as conn:
        row = conn.execute("SELECT embedding, embedding_model FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    if not row or row["embedding"] is None:
        return None, None
    return _unpack(row["embedding"]), row["embedding_model"]


def embedding_stats() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(embedding IS NOT NULL) AS embedded, SUM(pdf_path IS NOT NULL) AS pdfs FROM papers"
        ).fetchone()
    return {"total": int(row["total"] or 0), "embedded": int(row["embedded"] or 0), "pdfs": int(row["pdfs"] or 0)}


def rank_by_vector(vec: list[float], limit: int = 20, exclude: str | None = None,
                   model: str | None = None, view: str = "all", tags: list[str] | None = None) -> list[dict[str, Any]]:
    scored = []
    for arxiv_id, emb in all_embeddings(model):
        if arxiv_id == exclude:
            continue
        scored.append((cosine(vec, emb), arxiv_id))
    scored.sort(reverse=True)
    ids = [a for _, a in scored[: max(limit * 3, limit) if not tags else len(scored)]]
    if not ids:
        return []
    clauses, params = _filters(view, tags)
    extra = "".join(f" AND {c}" for c in clauses)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM papers WHERE arxiv_id IN ({','.join('?' * len(ids))}) {extra}", (*ids, *params)
        ).fetchall()
    by_id = {r["arxiv_id"]: _paper_row_to_dict(r) for r in rows}
    out = []
    for sim, arxiv_id in scored:
        if arxiv_id in by_id:
            d = by_id[arxiv_id]
            d["similarity"] = round(sim, 4)
            out.append(d)
            if len(out) >= limit:
                break
    return out


def preference_examples(limit: int = 10) -> dict[str, list[dict[str, str]]]:
    with connect() as conn:
        liked = conn.execute(
            "SELECT arxiv_id, title FROM papers WHERE reaction = 'like' ORDER BY reacted_at DESC LIMIT ?", (limit,)
        ).fetchall()
        disliked = conn.execute(
            "SELECT arxiv_id, title FROM papers WHERE reaction = 'dislike' ORDER BY reacted_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"liked": [dict(r) for r in liked], "disliked": [dict(r) for r in disliked]}


def preference_vector(model: str | None = None) -> list[float] | None:
    """Mean of liked embeddings minus mean of disliked embeddings; None until something is liked."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT reaction, embedding FROM papers WHERE reaction IN ('like', 'dislike') AND embedding IS NOT NULL"
            + (" AND embedding_model = ?" if model else ""),
            (model,) if model else (),
        ).fetchall()
    liked = [_unpack(r["embedding"]) for r in rows if r["reaction"] == "like"]
    disliked = [_unpack(r["embedding"]) for r in rows if r["reaction"] == "dislike"]
    if not liked:
        return None
    dim = len(liked[0])
    mean_like = [sum(v[i] for v in liked) / len(liked) for i in range(dim)]
    if disliked:
        mean_dis = [sum(v[i] for v in disliked) / len(disliked) for i in range(dim)]
        return [a - 0.5 * b for a, b in zip(mean_like, mean_dis)]
    return mean_like


def recompute_scores(model: str | None = None) -> int:
    pref = preference_vector(model)
    with connect() as conn:
        if pref is None:
            conn.execute("UPDATE papers SET score = NULL")
            return 0
        rows = conn.execute("SELECT arxiv_id, embedding FROM papers WHERE embedding IS NOT NULL").fetchall()
        updates = [(round(cosine(pref, _unpack(r["embedding"])), 4), r["arxiv_id"]) for r in rows]
        conn.executemany("UPDATE papers SET score = ? WHERE arxiv_id = ?", updates)
        return len(updates)


def score_for(vec: list[float], model: str | None = None) -> float | None:
    pref = preference_vector(model)
    return round(cosine(pref, vec), 4) if pref else None
