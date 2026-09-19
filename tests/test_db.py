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
