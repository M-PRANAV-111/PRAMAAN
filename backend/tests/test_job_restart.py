"""Failure and retry table, row "worker stopped mid-job": a job left RUNNING by a crash is re-queued when the worker
starts again and runs to completion (runs the real supervised worker, no mocks)."""
from __future__ import annotations

import os
import time
from unittest.mock import patch

from app.config import reset_settings_cache
from app.db import reader, transaction
from app.pipeline import orchestrator as jobs
from tests.local_support import LocalDatabaseCase


class RestartRecoveryTests(LocalDatabaseCase):
    def test_interrupted_job_is_requeued_and_finishes(self):
        with transaction() as c:
            job_id = jobs.create_job(c, "VALIDATE", "app")
            # What a crash leaves behind: the row says RUNNING but no worker owns it.
            c.execute("UPDATE jobs SET state='RUNNING', stage='Evaluating rule pack', stage_code='RULES' WHERE id=?", (job_id,))
        with patch.dict(os.environ, {"WORKER_THREADS": "1"}):
            reset_settings_cache()
            worker = jobs.Worker()
            worker.start()
            try:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    with reader() as c:
                        row = dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
                    if row["state"] in ("DONE", "FAILED"):
                        break
                    time.sleep(0.2)
            finally:
                worker.stop()
        reset_settings_cache()
        self.assertEqual((row["state"], row["stage_code"]), ("DONE", "DONE"))
        with reader() as c:
            runs = c.execute("SELECT COUNT(*) FROM validation_runs WHERE application_id='app'").fetchone()[0]
        self.assertEqual(runs, 1)  # the interrupted work was done once, after the restart
