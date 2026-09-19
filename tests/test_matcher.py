from app.services.matcher import match_paper

PAPER = {
    "title": "Continued Pretraining for Long Context Language Models",
    "abstract": "We study entity memorization and retrieval in transformers.",
}

def test_any_match():
    ok, tags = match_paper(PAPER, ["agents", "entity memorization"], "any")
    assert ok is True
    assert tags == ["entity memorization"]

def test_all_match_false():
    ok, _ = match_paper(PAPER, ["continued pretraining", "agents"], "all")
    assert ok is False

def test_empty_tags_matches_category_only():
    ok, tags = match_paper(PAPER, [], "any")
    assert ok is True
    assert tags == []
