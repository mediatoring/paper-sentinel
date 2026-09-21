from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app import db

log = logging.getLogger(__name__)
LIBRARY_DIR = db.DATA_DIR / "library"
MAX_TEXT_CHARS = 400_000
_throttle_lock = threading.Lock()
_last_download = 0.0


def library_dir() -> Path:
    d = db.DATA_DIR / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(arxiv_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", arxiv_id) + ".pdf"


def extract_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf not installed; PDF text will not be indexed")
        return ""
    try:
        reader = PdfReader(str(path))
        chunks = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            text = re.sub(r"[ \t]+", " ", text)
            chunks.append(text)
            total += len(text)
            if total > MAX_TEXT_CHARS:
                break
        return "\n".join(chunks)[:MAX_TEXT_CHARS].strip()
    except Exception as exc:
        log.warning("PDF text extraction failed for %s: %s", path, exc)
        return ""


def download_pdf(arxiv_id: str) -> dict[str, Any]:
    """Fetch the paper's PDF into the local library, extract its text and index it."""
    global _last_download
    paper = db.get_paper(arxiv_id)
    if paper is None:
        raise LookupError("Paper not found")
    target = library_dir() / safe_name(arxiv_id)
    if paper.get("has_pdf") and target.exists():
        return paper
    url = paper.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}"
    with _throttle_lock:
        wait = 3.0 - (time.monotonic() - _last_download)
        if wait > 0:
            time.sleep(wait)
        _last_download = time.monotonic()
    with httpx.Client(timeout=120.0, follow_redirects=True,
                      headers={"User-Agent": "PaperSentinel/0.1 (+https://github.com/mediatoring/paper-sentinel)"}) as client:
        resp = client.get(url)
        resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError("arXiv did not return a PDF (it may be rate limiting; try again in a minute)")
    target.write_bytes(resp.content)
    text = extract_text(target)
    updated = db.set_pdf(arxiv_id, target.name, len(resp.content), text)
    return updated or paper


def remove_pdf(arxiv_id: str) -> dict[str, Any] | None:
    path = db.get_pdf_path(arxiv_id)
    if path:
        try:
            (library_dir() / path).unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not delete %s: %s", path, exc)
    return db.set_pdf(arxiv_id, None, None, None)


def pdf_file(arxiv_id: str) -> Path | None:
    path = db.get_pdf_path(arxiv_id)
    if not path:
        return None
    file = library_dir() / path
    return file if file.exists() else None
