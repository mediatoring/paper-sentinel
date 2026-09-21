import importlib

import pytest


def _paper(arxiv_id, title, abstract):
    return {
        "arxiv_id": arxiv_id, "title": title, "abstract": abstract, "authors": [], "categories": ["cs.AI"],
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}", "pdf_url": None, "matched_tags": [],
    }


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    db.insert_paper(_paper("1", "Retrieval augmented agents", "We study retrieval for agents that plan."), {"summary": "Agents retrieve documents."})
    db.insert_paper(_paper("2", "Quantized transformers", "Low-bit quantization of attention layers."), {"summary": "Quantization works."})
    return db


def test_fts_query_building(db):
    assert db.fts_query('retrieval "long context" agents') == '"retrieval"* AND "long context" AND "agents"*'
    assert db.fts_query('a"b') == '"ab"*'
    assert db.fts_query("   ") == ""


def test_full_text_search_with_stemming(db):
    hits = db.search_text("retrieving")
    assert [h["arxiv_id"] for h in hits] == ["1"]
    assert "<mark>" in hits[0]["snippet"]
    assert db.search_text("quantization") and db.search_text("nothing-here") == []
    assert db.search_text("agents", view="saved") == []
    db.set_saved("1", True)
    assert [h["arxiv_id"] for h in db.search_text("agents", view="saved")] == ["1"]


def test_notes_and_tags_are_searchable(db):
    paper = db.set_notes("2", "Read for the brand-memory project", [" Brand memory ", "brand memory", "", "todo"])
    assert paper["notes"] == "Read for the brand-memory project"
    assert paper["user_tags"] == ["Brand memory", "todo"]
    assert [h["arxiv_id"] for h in db.search_text("brand")] == ["2"]
    assert db.all_user_tags() == ["Brand memory", "todo"]
    assert db.set_notes("missing", "x", []) is None


def test_pdf_text_is_indexed_and_hidden(db):
    paper = db.set_pdf("1", "1.pdf", 1234, "Section 3: we introduce zebra-striped memory cells.")
    assert paper["has_pdf"] and paper["has_fulltext"] and "pdf_text" not in paper
    assert [h["arxiv_id"] for h in db.search_text("zebra")] == ["1"]
    db.set_pdf("1", None, None, None)
    assert db.search_text("zebra") == []
    assert db.get_paper("1")["has_pdf"] is False


def test_embeddings_similarity_and_preference_scores(db):
    assert db.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert db.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert db.cosine([], [1]) == 0.0
    db.insert_paper(_paper("3", "Agent memory", "Memory for agents."), {})
    db.set_embedding("1", [1.0, 0.0, 0.0], "m")
    db.set_embedding("2", [0.0, 1.0, 0.0], "m")
    db.set_embedding("3", [0.9, 0.1, 0.0], "m")
    assert {p["arxiv_id"] for p in db.papers_without_embedding("m")} == set()
    assert {p["arxiv_id"] for p in db.papers_without_embedding("other")} == {"1", "2", "3"}

    similar = db.rank_by_vector([1.0, 0.0, 0.0], limit=2, exclude="1", model="m")
    assert [p["arxiv_id"] for p in similar] == ["3", "2"]
    assert similar[0]["similarity"] > similar[1]["similarity"]

    assert db.preference_vector("m") is None
    assert db.recompute_scores("m") == 0
    db.set_reaction("1", "like")
    db.set_reaction("2", "dislike")
    assert db.recompute_scores("m") == 3
    ranked = db.list_papers(view="all", sort="score")
    assert [p["arxiv_id"] for p in ranked] == ["1", "3", "2"]
    assert db.score_for([0.9, 0.1, 0.0], "m") > db.score_for([0.0, 1.0, 0.0], "m")
    assert db.embedding_stats() == {"total": 3, "embedded": 3, "pdfs": 0}
    prefs = db.preference_examples()
    assert [p["arxiv_id"] for p in prefs["liked"]] == ["1"] and [p["arxiv_id"] for p in prefs["disliked"]] == ["2"]


def test_fts_backfill_on_existing_database(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    tmp_path.mkdir(exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH)
    conn.executescript("""
        CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY, title TEXT NOT NULL, abstract TEXT NOT NULL,
            authors TEXT NOT NULL, categories TEXT NOT NULL, published TEXT, updated TEXT,
            abs_url TEXT NOT NULL, pdf_url TEXT, matched_tags TEXT NOT NULL, summary TEXT,
            why_relevant TEXT, key_contribution TEXT, limitations TEXT, related_to TEXT, created_at TEXT NOT NULL);
        INSERT INTO papers VALUES ('old','Sparse mixture of experts','Routing tokens.','[]','[]',NULL,NULL,'u',NULL,'[]','','','','','','2026-01-01');
    """)
    conn.commit(); conn.close()
    db.init_db()
    assert [h["arxiv_id"] for h in db.search_text("experts")] == ["old"]
    assert db.get_paper("old")["user_tags"] == []
