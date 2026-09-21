from __future__ import annotations

import json
import re
from typing import Any

import httpx

WORD_TARGETS = {"short": 70, "medium": 160, "long": 320}


def _fallback(paper: dict[str, Any], matched_tags: list[str]) -> dict[str, str]:
    sentences = re.split(r"(?<=[.!?])\s+", paper.get("abstract", ""))
    summary = " ".join(sentences[:3]).strip()
    tags = ", ".join(matched_tags) if matched_tags else "selected categories"
    return {
        "summary": summary,
        "why_relevant": f"Matched your research radar via: {tags}.",
        "key_contribution": sentences[0] if sentences else summary,
        "limitations": "Not assessed: local LLM is disabled or unavailable.",
        "related_to": "",
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _preference_block(preferences: dict[str, list[dict[str, str]]] | None) -> str:
    if not preferences:
        return ""
    liked = "\n".join(f"- {p['title']}" for p in preferences.get("liked", [])[:10])
    disliked = "\n".join(f"- {p['title']}" for p in preferences.get("disliked", [])[:10])
    if not liked and not disliked:
        return ""
    block = "\nUSER PREFERENCES (learned from explicit feedback; use them to judge relevance, not to invent facts):"
    if liked:
        block += f"\nPapers the user marked as useful:\n{liked}"
    if disliked:
        block += f"\nPapers the user marked as not interesting:\n{disliked}"
    return block + "\n"


def analyze_paper(
    paper: dict[str, Any],
    settings: dict[str, Any],
    matched_tags: list[str],
    recent: list[dict[str, str]],
    preferences: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, str]:
    if not settings.get("llm_enabled"):
        return _fallback(paper, matched_tags)

    base_url = settings.get("llm_base_url", "").rstrip("/")
    if not base_url:
        return _fallback(paper, matched_tags)
    target = WORD_TARGETS.get(settings.get("summary_length", "medium"), 160)
    context = "\n".join(
        f"- {p['arxiv_id']}: {p['title']} — {p.get('key_contribution', '')}"
        for p in recent[:20]
    ) or "No prior papers stored yet."
    prompt = f"""
You are Paper Sentinel, a precise research-radar agent. Analyze the arXiv paper below.
Do not invent findings that are not supported by the title/abstract. Clearly separate author claims from your inference.
The user's selected research tags are: {', '.join(matched_tags) or 'category match'}.
Write the summary at roughly {target} words.

Return ONLY valid JSON with these string fields:
summary, why_relevant, key_contribution, limitations, related_to

In why_relevant, relate the paper to the user's tags and, when preferences are given, to what they liked or disliked.
{_preference_block(preferences)}
For related_to, mention only papers from the recent-paper list when there is a plausible topical relation. Otherwise use an empty string.

RECENT PAPERS:
{context}

PAPER:
Title: {paper['title']}
Authors: {', '.join(paper['authors'])}
Categories: {', '.join(paper['categories'])}
Abstract: {paper['abstract']}
""".strip()

    headers = {"Content-Type": "application/json"}
    if settings.get("llm_api_key"):
        headers["Authorization"] = f"Bearer {settings['llm_api_key']}"
    payload = {
        "model": settings.get("llm_model") or "local-model",
        "messages": [
            {"role": "system", "content": "Be factual, concise, and return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(settings.get("llm_temperature", 0.2)),
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        result = _extract_json(data["choices"][0]["message"]["content"])
        return {
            key: str(result.get(key, "")).strip()
            for key in ("summary", "why_relevant", "key_contribution", "limitations", "related_to")
        }
    except Exception:
        return _fallback(paper, matched_tags)
