from __future__ import annotations

ARXIV_CATEGORIES = [
    ("cs.AI", "Artificial Intelligence"),
    ("cs.CL", "Computation and Language"),
    ("cs.CV", "Computer Vision and Pattern Recognition"),
    ("cs.LG", "Machine Learning"),
    ("cs.NE", "Neural and Evolutionary Computing"),
    ("cs.RO", "Robotics"),
    ("stat.ML", "Machine Learning (Statistics)"),
    ("cs.IR", "Information Retrieval"),
    ("cs.HC", "Human-Computer Interaction"),
    ("cs.MA", "Multiagent Systems"),
    ("cs.SE", "Software Engineering"),
    ("cs.DB", "Databases"),
    ("cs.CR", "Cryptography and Security"),
    ("cs.DC", "Distributed and Parallel Computing"),
    ("cs.SD", "Sound"),
    ("cs.CY", "Computers and Society"),
    ("cs.GT", "Game Theory"),
    ("cs.SI", "Social and Information Networks"),
    ("eess.AS", "Audio and Speech Processing"),
    ("eess.IV", "Image and Video Processing"),
    ("q-bio.NC", "Neurons and Cognition"),
    ("math.OC", "Optimization and Control"),
    ("econ.EM", "Econometrics"),
]

# arXiv category ids look like "cs.IR", "stat.ML", "q-bio.NC", "hep-th" or "math.OC".
CATEGORY_PATTERN = r"^[a-z][a-z-]*(\.[A-Za-z][A-Za-z-]*)?$"


def normalize_categories(values: list[str]) -> tuple[list[str], list[str]]:
    """Return (valid, rejected) category ids, de-duplicated and in the given order."""
    import re

    valid: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in values:
        code = str(raw or "").strip()
        if not code:
            continue
        if not re.match(CATEGORY_PATTERN, code):
            rejected.append(code)
            continue
        key = code.lower()
        if key in seen:
            continue
        seen.add(key)
        valid.append(code)
    return valid, rejected

SUGGESTED_TAGS = [
    "agents", "alignment", "attention", "benchmark", "continual learning",
    "continued pretraining", "distillation", "embeddings", "evaluation",
    "fine-tuning", "foundation models", "interpretability", "long context",
    "memorization", "multimodal", "quantization", "reasoning", "retrieval",
    "RAG", "robotics", "safety", "scaling", "synthetic data", "transformers",
    "vision-language", "world models",
]

DEFAULT_SETTINGS = {
    "categories": ["cs.AI", "cs.CL", "cs.LG"],
    "tags": ["agents", "reasoning", "continued pretraining"],
    "match_mode": "any",
    "interval_minutes": 360,
    "max_results": 100,
    "summary_length": "medium",
    "view_mode": "cards3",
    "llm_enabled": True,
    "llm_base_url": "http://127.0.0.1:1234/v1",
    "llm_model": "local-model",
    "llm_api_key": "",
    "llm_temperature": 0.2,
    "embeddings_enabled": True,
    "embedding_model": "",
    "library_auto_download": True,
    "browser_notifications": True,
    "email_enabled": False,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_to": "",
    "smtp_starttls": True,
    "webhook_enabled": False,
    "webhook_url": "",
}

VIEW_MODES = ("cards2", "cards3", "table")
# Older databases stored these names; map them to the current set.
LEGACY_VIEW_MODES = {"cards": "cards3", "compact": "table"}


def normalize_view_mode(value: str | None) -> str:
    value = LEGACY_VIEW_MODES.get(value or "", value or "")
    return value if value in VIEW_MODES else "cards3"
