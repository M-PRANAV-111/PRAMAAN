"""Private, content-addressed file storage.

Files are stored by SHA-256 under ``DATA_DIR/files/ab/cdef...``. User-supplied names never touch the
filesystem, so path traversal is impossible by construction. Swap for an S3-compatible backend by
implementing the same three methods.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .config import get_settings

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().storage_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str) -> Path:
        if not _SHA_RE.match(sha256):
            raise ValueError("invalid object key")
        return self.root / sha256[:2] / sha256[2:]

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.chmod(tmp, 0o600)
            tmp.replace(path)
        return sha

    def get(self, sha256: str) -> bytes:
        data = self._path(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise IOError("stored object failed integrity check")
        return data

    def exists(self, sha256: str) -> bool:
        return self._path(sha256).exists()


def safe_display_name(name: str) -> str:
    """Display-only file name: strip directories and control characters, cap length."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^\w.\- ()]+", "_", base).strip(" ._") or "document"
    return base[:120]
