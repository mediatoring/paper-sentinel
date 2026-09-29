from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app import db
from app.services.scanner import scan_once

log = logging.getLogger(__name__)
scheduler = BackgroundScheduler(daemon=True)
JOB_ID = "paper-sentinel-scan"
RETRY_JOB_ID = "paper-sentinel-retry"
RETRY_MINUTES = 15
MAX_RETRIES = 12  # 12 x 15 min = 3 hours of retries before giving up until the next regular scan


def run_scan() -> dict[str, Any]:
    """Run a scan and, when arXiv could not be fetched, schedule a retry in RETRY_MINUTES."""
    result = scan_once()
    if result.get("status") == "ok":
        db.set_state("retry_count", "0")
        db.set_state("next_retry", "")
        if scheduler.running and scheduler.get_job(RETRY_JOB_ID):
            scheduler.remove_job(RETRY_JOB_ID)
    elif result.get("status") == "error" and result.get("retryable"):
        schedule_retry()
    return result


def schedule_retry() -> str | None:
    count = int(db.get_state().get("retry_count") or 0)
    if count >= MAX_RETRIES or not scheduler.running:
        db.set_state("next_retry", "")
        return None
    when = datetime.now(timezone.utc) + timedelta(minutes=RETRY_MINUTES)
    scheduler.add_job(run_scan, "date", run_date=when, id=RETRY_JOB_ID, replace_existing=True, misfire_grace_time=600)
    db.set_state("retry_count", str(count + 1))
    db.set_state("next_retry", when.isoformat())
    log.info("arXiv fetch failed; retry %d/%d scheduled at %s", count + 1, MAX_RETRIES, when.isoformat())
    return when.isoformat()


def reschedule() -> None:
    settings = db.get_settings()
    minutes = max(30, int(settings.get("interval_minutes", 360)))
    if scheduler.get_job(JOB_ID):
        scheduler.reschedule_job(JOB_ID, trigger="interval", minutes=minutes)
    else:
        scheduler.add_job(run_scan, "interval", minutes=minutes, id=JOB_ID, max_instances=1, coalesce=True)


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reschedule()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
