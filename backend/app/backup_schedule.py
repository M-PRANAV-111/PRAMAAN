import logging
import threading
from datetime import datetime, timezone

from .config import get_settings


def start_schedule():
    stop=threading.Event()
    if not get_settings().backup_schedule:
        return stop
    def loop():
        from scripts.backup import create_backup
        last=None
        while not stop.is_set():
            now=datetime.now(timezone.utc)
            if now.hour==get_settings().backup_hour_utc and last!=now.date():
                try:
                    create_backup()
                    last=now.date()
                except Exception as exc:
                    logging.getLogger('pramaan.backup').error('backup_failure code=%s',type(exc).__name__)
            stop.wait(60)
    threading.Thread(target=loop,name='pramaan-backup',daemon=True).start()
    return stop
