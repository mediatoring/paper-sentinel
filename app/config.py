from __future__ import annotations

ARXIV_CATEGORIES = [
    ("cs.AI", "Artificial Intelligence"),
    ("cs.CL", "Computation and Language"),
    ("cs.CV", "Computer Vision and Pattern Recognition"),
    ("cs.LG", "Machine Learning"),
    ("cs.NE", "Neural and Evolutionary Computing"),
    ("cs.RO", "Robotics"),
    ("stat.ML", "Machine Learning (Statistics)"),
]

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
    "view_mode": "cards",
    "llm_enabled": True,
    "llm_base_url": "http://127.0.0.1:1234/v1",
    "llm_model": "local-model",
    "llm_api_key": "",
    "llm_temperature": 0.2,
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
