import importlib

from app.services.arxiv import FetchError


def test_retry_scheduled_only_for_fetch_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_SENTINEL_DATA", str(tmp_path))
    import app.db as db
    importlib.reload(db)
    db.init_db()
    import app.scheduler as sched
    importlib.reload(sched)
    sched.scheduler.start(paused=True)
    try:
        monkeypatch.setattr(sched, "scan_once", lambda: {"status": "error", "error": "x", "retryable": True})
        result = sched.run_scan()
        assert result["status"] == "error"
        assert sched.scheduler.get_job(sched.RETRY_JOB_ID) is not None
        assert db.get_state()["retry_count"] == "1" and db.get_state()["next_retry"]

        monkeypatch.setattr(sched, "scan_once", lambda: {"status": "error", "error": "llm", "retryable": False})
        sched.run_scan()
        assert db.get_state()["retry_count"] == "1"  # not incremented for non-fetch errors

        monkeypatch.setattr(sched, "scan_once", lambda: {"status": "ok"})
        sched.run_scan()
        assert sched.scheduler.get_job(sched.RETRY_JOB_ID) is None
        assert db.get_state()["retry_count"] == "0" and db.get_state()["next_retry"] == ""

        db.set_state("retry_count", str(sched.MAX_RETRIES))
        assert sched.schedule_retry() is None
    finally:
        sched.scheduler.shutdown(wait=False)


def test_fetch_error_is_raised_for_unreachable_api(monkeypatch):
    import httpx
    from app.services import arxiv

    def boom(request):
        raise httpx.ConnectError("down", request=request)

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real(transport=httpx.MockTransport(boom), **{k: v for k, v in kw.items() if k != "transport"}))
    monkeypatch.setattr(arxiv, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(arxiv.time, "sleep", lambda s: None)
    try:
        arxiv.fetch_latest(["cs.AI"], 5)
    except FetchError as exc:
        assert "RSS fallback" in str(exc)
    else:
        raise AssertionError("expected FetchError")
