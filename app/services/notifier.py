from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import httpx


def _digest(new_papers: list[dict[str, Any]]) -> str:
    lines = [f"Paper Sentinel found {len(new_papers)} new relevant paper(s).", ""]
    for p in new_papers[:20]:
        lines.extend([
            p["title"],
            p.get("key_contribution") or p.get("summary", ""),
            p["abs_url"],
            "",
        ])
    return "\n".join(lines)


def send_notifications(settings: dict[str, Any], new_papers: list[dict[str, Any]]) -> None:
    if not new_papers:
        return
    digest = _digest(new_papers)
    if settings.get("email_enabled") and settings.get("smtp_host") and settings.get("smtp_to"):
        msg = EmailMessage()
        msg["Subject"] = f"Paper Sentinel: {len(new_papers)} new paper(s)"
        msg["From"] = settings.get("smtp_from") or settings.get("smtp_username")
        msg["To"] = settings["smtp_to"]
        msg.set_content(digest)
        try:
            with smtplib.SMTP(settings["smtp_host"], int(settings.get("smtp_port", 587)), timeout=30) as smtp:
                if settings.get("smtp_starttls", True):
                    smtp.starttls()
                if settings.get("smtp_username"):
                    smtp.login(settings["smtp_username"], settings.get("smtp_password", ""))
                smtp.send_message(msg)
        except Exception:
            pass

    if settings.get("webhook_enabled") and settings.get("webhook_url"):
        try:
            httpx.post(
                settings["webhook_url"],
                json={"text": digest, "papers": new_papers[:20]},
                timeout=20.0,
            ).raise_for_status()
        except Exception:
            pass
