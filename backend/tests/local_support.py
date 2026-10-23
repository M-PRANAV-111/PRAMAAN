import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import reset_settings_cache
from app.db import now_iso, transaction


class LocalDatabaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name,'DATABASE_PATH':'','WORKER_THREADS':'0',
                            'APP_ENV':'test','EMAIL_PROVIDER':'console','BACKUP_SCHEDULE':'false','NOTIFY_EMAIL':'false',
                            'SENTRY_DSN':'','BACKUP_S3_ENDPOINT':'','BACKUP_S3_BUCKET':'','BACKUP_S3_KEY_ID':'','BACKUP_S3_SECRET':''})
        self.env.start()
        reset_settings_cache()
        from app.main import bootstrap
        bootstrap()
        with transaction() as c:
            ts=now_iso()
            c.execute("INSERT INTO institutions (id,aicte_permanent_id,name,state,trust_name,created_at) VALUES ('ins','1-SYN-TEST','Synthetic institute','Test','Test trust',?)",(ts,))
            c.execute("INSERT INTO users (id,email,name,role,institution_id,password_hash,created_at) VALUES ('usr','contact@example.test','Test contact','INSTITUTION','ins',?,?)",('!unused-'+secrets.token_hex(16),ts))
            c.execute("INSERT INTO applications (id,institution_id,category,academic_year,status,created_by,created_at,updated_at,submitted_at) VALUES ('app','ins','EOA_EXISTING','2026-27','DRAFT','usr',?,?,?)",(ts,ts,ts))

    def tearDown(self):
        from app.email import drain
        drain()
        self.env.stop()
        reset_settings_cache()
        self.tmp.cleanup()
