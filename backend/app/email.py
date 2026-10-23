"""Prototype email delivery on a dedicated worker; log only sanitized failure codes."""
import json
import logging
import os
import queue
import re
import smtplib
import ssl
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from uuid import uuid4

import requests

from .config import get_settings

log = logging.getLogger("pramaan.email")
_queue = queue.Queue()
_thread = None
_lock = threading.Lock()
failures = 0


def send_email(to, subject, text, html=None):
    """Enqueue mail; provider I/O never blocks the request handler."""
    start()
    _queue.put((to, subject, text, html))


def start():
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, name="pramaan-email", daemon=True)
            _thread.start()


def _deliver(to, subject, text, html):
    s = get_settings()
    text = "From the PRAMAAN prototype.\n\n" + text
    if html:
        html = '<p style="color:#1d2b4f;background:#f2f5f0">From the PRAMAAN prototype.</p>' + html
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    if s.email_provider == "console":
        if s.env == "production":
            raise RuntimeError("console_disabled")
        out = s.data_dir / "outbox"
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        purpose = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:50]
        path = out / f"{stamp}-{purpose}-{uuid4().hex[:8]}.eml"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(msg.as_bytes())
        with (out / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": stamp, "purpose": purpose, "file": path.name}) + "\n")
    elif s.email_provider == "smtp":
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    else:
        payload = {"from": s.email_from, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        response = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {s.resend_api_key}"},
                                 json=payload, timeout=20, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise DeliveryError(f"http_{response.status_code}")


class DeliveryError(Exception):
    pass


def _loop():
    global failures
    while True:
        args = _queue.get()
        try:
            for attempt in range(3):
                try:
                    _deliver(*args)
                    break
                except Exception as exc:
                    failures += 1
                    code = str(exc) if isinstance(exc, DeliveryError) else (
                        f"smtp_{exc.smtp_code}" if isinstance(exc, smtplib.SMTPResponseException) else type(exc).__name__)
                    log.warning("email_failure code=%s", code)
                    from .db import transaction, now_iso
                    try:
                        with transaction() as c:
                            c.execute('INSERT INTO email_failures (provider,error_code,created_at) VALUES (?,?,?)',
                                      (get_settings().email_provider,code,now_iso()))
                    except Exception:
                        log.warning('email_failure_metric code=storage_unavailable')
                    if attempt < 2:
                        time.sleep((2, 8)[attempt])
        finally:
            _queue.task_done()


def drain(timeout=30):
    end = time.monotonic() + timeout
    while _queue.unfinished_tasks and time.monotonic() < end:
        time.sleep(.02)
