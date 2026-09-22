import importlib


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    s = db.get_settings()
    s["interval_minutes"] = 10
    saved = db.save_settings(s)
    assert saved["interval_minutes"] == 30
    assert db.get_settings()["interval_minutes"] == 30


def _paper(arxiv_id):
    return {
        "arxiv_id": arxiv_id, "title": "T", "abstract": "A", "authors": [], "categories": ["cs.AI"],
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}", "pdf_url": None, "matched_tags": ["agents"],
    }


def test_read_later_shelf(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    db.insert_paper(_paper("1"), {})
    db.insert_paper(_paper("2"), {})
    assert db.count_saved() == 0
    assert db.list_papers(saved_only=True) == []
    assert db.set_saved("missing", True) is None

    saved = db.set_saved("2", True)
    assert saved["saved"] is True and saved["saved_at"]
    assert [p["arxiv_id"] for p in db.list_papers(saved_only=True)] == ["2"]
    assert db.count_saved() == 1
    assert {p["arxiv_id"]: p["saved"] for p in db.list_papers()} == {"1": False, "2": True}

    db.set_saved("2", False)
    assert db.count_saved() == 0
    assert db.list_papers(saved_only=True) == []


def test_migration_adds_saved_columns(tmp_path, monkeypatch):
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
        INSERT INTO papers VALUES ('old','T','A','[]','[]',NULL,NULL,'u',NULL,'[]','','','','','','2026-01-01');
    """)
    conn.commit(); conn.close()
    db.init_db()
    papers = db.list_papers()
    assert papers[0]["arxiv_id"] == "old" and papers[0]["saved"] is False
    assert db.set_saved("old", True)["saved"] is True


def test_reactions(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    db.insert_paper(_paper("a"), {})
    db.insert_paper(_paper("b"), {})
    assert db.list_papers()[0]["reaction"] is None
    assert db.set_reaction("missing", "like") is None
    with pytest.raises(ValueError):
        db.set_reaction("a", "meh")

    liked = db.set_reaction("a", "like")
    assert liked["reaction"] == "like" and liked["reacted_at"]
    db.set_reaction("b", "dislike")
    assert [p["arxiv_id"] for p in db.list_papers(view="liked")] == ["a"]
    assert [p["arxiv_id"] for p in db.list_papers(view="disliked")] == ["b"]
    assert db.counts() == {"total": 2, "saved": 0, "liked": 1, "disliked": 1, "inbox": 0, "read": 0}

    assert db.set_reaction("a", None)["reaction"] is None
    assert db.list_papers(view="liked") == []
    assert db.counts()["liked"] == 0
    assert len(db.list_papers(view="all")) == 2


def test_view_mode_normalization(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    assert db.get_settings()["view_mode"] == "cards3"
    for stored, expected in (("cards", "cards3"), ("compact", "table"), ("table", "table"), ("cards2", "cards2"), ("bogus", "cards3")):
        s = db.get_settings()
        s["view_mode"] = stored
        assert db.save_settings(s)["view_mode"] == expected
        assert db.get_settings()["view_mode"] == expected


def test_normalize_categories():
    from app.config import normalize_categories
    valid, rejected = normalize_categories(["cs.AI", " cs.IR ", "q-bio.NC", "hep-th", "cs.ai", "", "not a cat", "CS.LG", "physics.comp-ph"])
    assert valid == ["cs.AI", "cs.IR", "q-bio.NC", "hep-th", "physics.comp-ph"]
    assert rejected == ["not a cat", "CS.LG"]


def test_inbox_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    for i in "abcd":
        db.insert_paper(_paper(i), {})
    assert {p["arxiv_id"] for p in db.list_papers(view="inbox")} == set("abcd")
    db.set_saved("a", True)
    db.set_reaction("b", "like")
    db.set_read("c", True)
    assert [p["arxiv_id"] for p in db.list_papers(view="inbox")] == ["d"]
    assert db.counts()["inbox"] == 1 and db.counts()["read"] == 1
    assert db.set_read("c", False)["read_at"] is None
    assert {p["arxiv_id"] for p in db.list_papers(view="inbox")} == {"c", "d"}
    assert db.mark_all_read() == 2
    assert db.list_papers(view="inbox") == []
    assert len(db.list_papers(view="all")) == 4
    assert db.set_read("missing", True) is None


def test_paper_exists_ignores_version(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    db.insert_paper(_paper("2609.20822v1"), {})
    assert db.paper_exists("2609.20822v1")
    assert db.paper_exists("2609.20822v2")
    assert db.paper_exists("2609.20822")
    assert not db.paper_exists("2609.20823v1")
    assert not db.paper_exists("2609.2082v1")
    assert db.base_arxiv_id("hep-th/9901001v2") == "hep-th/9901001"


def test_folders(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    for i in "abc":
        db.insert_paper(_paper(i), {})
    phd = db.create_folder("  PhD studium ")
    sec = db.create_folder("Kyberbezpečnost")
    assert phd["name"] == "PhD studium" and phd["count"] == 0
    with pytest.raises(ValueError):
        db.create_folder("phd STUDIUM")
    with pytest.raises(ValueError):
        db.create_folder("KYBERBEZPEČNOST")
    with pytest.raises(ValueError):
        db.create_folder("   ")

    paper = db.set_paper_folders("a", [phd["id"], sec["id"], 999])
    assert [f["name"] for f in paper["folders"]] == ["PhD studium", "Kyberbezpečnost"]
    db.set_paper_folders("b", [sec["id"]])
    assert {f["name"]: f["count"] for f in db.list_folders()} == {"PhD studium": 1, "Kyberbezpečnost": 2}
    assert {p["arxiv_id"] for p in db.list_papers(view="folder", folder=sec["id"])} == {"a", "b"}
    assert [p["arxiv_id"] for p in db.list_papers(view="inbox")] == ["c"]
    assert db.counts()["inbox"] == 1
    assert db.get_paper("c")["folders"] == []
    assert [h["arxiv_id"] for h in db.search_text("T", folder=phd["id"])] == ["a"]

    assert db.rename_folder(phd["id"], "Dizertace")["name"] == "Dizertace"
    with pytest.raises(ValueError):
        db.rename_folder(phd["id"], "kyberbezpečnost")
    assert db.rename_folder(999, "x") is None
    assert db.set_paper_folders("a", []) ["folders"] == []
    assert db.counts()["inbox"] == 2
    assert db.delete_folder(sec["id"]) and not db.delete_folder(sec["id"])
    assert db.get_paper("b")["folders"] == []
    assert db.set_paper_folders("missing", [phd["id"]]) is None
