from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import feedparser
import httpx

log = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_RSS = "https://rss.arxiv.org/atom/{categories}"
USER_AGENT = "PaperSentinel/0.1 (open-source research radar; +https://github.com/mediatoring/paper-sentinel)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/xml, text/xml, */*"}

# arXiv asks API clients to wait at least 3 seconds between requests. When the
# limit is exceeded it answers with an empty 406 or 429 (and later times out).
MIN_REQUEST_INTERVAL = 3.0
RETRY_STATUSES = {406, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _get(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET with polite throttling and exponential backoff on arXiv rate limiting."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _throttle()
        try:
            with httpx.Client(timeout=30.0, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(url, params=params)
            if response.status_code in RETRY_STATUSES:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 3.0 * (2 ** (attempt - 1))
                last_error = httpx.HTTPStatusError(
                    f"arXiv responded {response.status_code} (rate limited)", request=response.request, response=response
                )
                log.warning("arXiv %s on attempt %d/%d, retrying in %.0fs", response.status_code, attempt, MAX_ATTEMPTS, delay)
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as exc:
            last_error = exc
            log.warning("arXiv request failed on attempt %d/%d: %s", attempt, MAX_ATTEMPTS, exc)
            time.sleep(3.0 * (2 ** (attempt - 1)))
    raise RuntimeError(f"arXiv request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _arxiv_id_from(entry: Any) -> str:
    raw = getattr(entry, "id", "") or getattr(entry, "link", "")
    raw = raw.rstrip("/")
    # API: http://arxiv.org/abs/2509.12345v1   RSS: oai:arXiv.org:2509.12345v1
    return raw.split("/")[-1].split(":")[-1]


def _authors_from(entry: Any) -> list[str]:
    names = [a.get("name", "") for a in getattr(entry, "authors", []) if a.get("name")]
    if not names and getattr(entry, "author", ""):
        names = [entry.author]
    # RSS feeds put all authors into one dc:creator string: "A, B, C"
    authors: list[str] = []
    for name in names:
        authors.extend(part.strip() for part in name.split(",") if part.strip())
    return authors


def _abstract_from(entry: Any) -> str:
    text = getattr(entry, "summary", "") or ""
    # RSS feeds prefix the abstract with "arXiv:ID Announce Type: new \nAbstract: ..."
    text = re.sub(r"^arXiv:\S+\s+Announce Type:\s*\S+\s*", "", text.strip())
    text = re.sub(r"^Abstract:\s*", "", text)
    return _clean(text)


def parse_feed(text: str) -> list[dict[str, Any]]:
    feed = feedparser.parse(text)
    papers: list[dict[str, Any]] = []
    for entry in feed.entries:
        arxiv_id = _arxiv_id_from(entry)
        if not arxiv_id:
            continue
        links = getattr(entry, "links", [])
        pdf_url = next((l.get("href") for l in links if l.get("title") == "pdf"), None)
        abs_url = getattr(entry, "link", "") or f"https://arxiv.org/abs/{arxiv_id}"
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        papers.append({
            "arxiv_id": arxiv_id,
            "title": _clean(getattr(entry, "title", "")),
            "abstract": _abstract_from(entry),
            "authors": _authors_from(entry),
            "categories": [t.get("term") for t in getattr(entry, "tags", []) if t.get("term")],
            "published": getattr(entry, "published", None),
            "updated": getattr(entry, "updated", None),
            "abs_url": abs_url,
            "pdf_url": pdf_url,
        })
    return papers


def fetch_latest(categories: list[str], max_results: int = 100) -> list[dict[str, Any]]:
    if not categories:
        return []
    params = {
        "search_query": " OR ".join(f"cat:{c}" for c in categories),
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        return parse_feed(_get(ARXIV_API, params).text)
    except Exception as api_error:
        log.warning("arXiv API unavailable (%s); falling back to rss.arxiv.org", api_error)
        try:
            papers = parse_feed(_get(ARXIV_RSS.format(categories="+".join(categories))).text)
        except Exception as rss_error:
            raise RuntimeError(f"arXiv API: {api_error}; RSS fallback: {rss_error}") from rss_error
        if not papers:
            raise RuntimeError(
                f"arXiv API is rate limiting this client ({api_error}); the RSS fallback has no new "
                "announcements right now (arXiv publishes on weekdays only). Try again later."
            ) from api_error
        return papers[:max_results]
