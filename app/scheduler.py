from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app import db
from app.services.scanner import scan_once

scheduler = BackgroundScheduler(daemon=True)
JOB_ID = "paper-sentinel-scan"


def reschedule() -> None:
    settings = db.get_settings()
    minutes = max(30, int(settings.get("interval_minutes", 360)))
    if scheduler.get_job(JOB_ID):
        scheduler.reschedule_job(JOB_ID, trigger="interval", minutes=minutes)
    else:
        scheduler.add_job(scan_once, "interval", minutes=minutes, id=JOB_ID, max_instances=1, coalesce=True)


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reschedule()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
