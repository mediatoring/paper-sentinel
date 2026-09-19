from __future__ import annotations

import re
from typing import Any


def match_paper(paper: dict[str, Any], tags: list[str], mode: str = "any") -> tuple[bool, list[str]]:
    if not tags:
        return True, []
    haystack = f"{paper.get('title', '')}\n{paper.get('abstract', '')}".lower()
    matched: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized:
            continue
        pattern = r"(?<!\w)" + re.escape(normalized) + r"(?!\w)"
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            matched.append(tag)
    if mode == "all":
        expected = len([t for t in tags if t.strip()])
        return len(matched) == expected, matched
    return bool(matched), matched
