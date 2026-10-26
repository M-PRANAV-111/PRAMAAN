"""Failure and retry table, rows "database / storage / OCR unavailable": the readiness probe answers 503 with the
failing check named, and 200 when everything is available."""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

from app.routes import system
from tests.local_support import LocalDatabaseCase


def probe() -> tuple[int, dict]:
    response = system.ready(None)
    return response.status_code, json.loads(response.body)


class ReadinessTests(LocalDatabaseCase):
    def test_all_available(self):
        with patch.object(system.shutil, "which", return_value="tesseract"):
            status, body = probe()
        self.assertEqual((status, body["status"]), (200, "ok"))
        self.assertEqual(body["checks"]["database"], "ok")

    def test_database_unavailable(self):
        @contextmanager
        def broken():
            raise OSError("synthetic database outage")
            yield  # pragma: no cover
        with patch.object(system, "reader", broken), patch.object(system.shutil, "which", return_value="tesseract"):
            status, body = probe()
        self.assertEqual((status, body["status"]), (503, "degraded"))
        self.assertTrue(body["checks"]["database"].startswith("error"))

    def test_storage_unavailable(self):
        with patch.object(system, "LocalStorage", side_effect=OSError("synthetic storage outage")), \
                patch.object(system.shutil, "which", return_value="tesseract"):
            status, body = probe()
        self.assertEqual((status, body["checks"]["storage"]), (503, "error"))

    def test_ocr_unavailable(self):
        settings = system.get_settings().model_copy(update={"tesseract_cmd": ""})
        with patch.object(system, "get_settings", lambda: settings), patch.object(system.shutil, "which", return_value=None):
            status, body = probe()
        self.assertEqual(status, 503)
        self.assertTrue(body["checks"]["ocr"].startswith("unavailable"))
