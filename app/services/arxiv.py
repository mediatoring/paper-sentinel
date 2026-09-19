from __future__ import annotations

import re
from typing import Any

import feedparser
import httpx

ARXIV_API = "https://export.arxiv.org/api/query"
USER_AGENT = "PaperSentinel/0.1 (open-source research radar)"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_latest(categories: list[str], max_results: int = 100) -> list[dict[str, Any]]:
    if not categories:
        return []
    query = " OR ".join(f"cat:{c}" for c in categories)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    with httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(ARXIV_API, params=params)
        response.raise_for_status()
    feed = feedparser.loads(response.text)
    papers: list[dict[str, Any]] = []
    for entry in feed.entries:
        arxiv_id = entry.id.rstrip("/").split("/")[-1]
        links = {getattr(link, "type", ""): link.href for link in getattr(entry, "links", [])}
        pdf_url = next((link.href for link in getattr(entry, "links", []) if getattr(link, "title", "") == "pdf"), None)
        papers.append({
            "arxiv_id": arxiv_id,
            "title": _clean(entry.title),
            "abstract": _clean(entry.summary),
            "authors": [a.name for a in getattr(entry, "authors", [])],
            "categories": [t.term for t in getattr(entry, "tags", [])],
            "published": getattr(entry, "published", None),
            "updated": getattr(entry, "updated", None),
            "abs_url": entry.link,
            "pdf_url": pdf_url,
        })
    return papers
