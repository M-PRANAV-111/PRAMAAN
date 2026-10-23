"""Upload validation: content-based type detection and resource limits before anything is stored."""
from __future__ import annotations

import io
from dataclasses import dataclass

import pikepdf
from PIL import Image

from .doctypes import IMAGE_DOC_TYPES

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard

_MAGIC = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}


class IntakeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class IntakeResult:
    mime: str
    pages: int


def sniff(data: bytes) -> str | None:
    head = data[:1024]
    for magic, mime in _MAGIC.items():
        if head.startswith(magic) or (magic == b"%PDF-" and magic in head[:1024]):
            return mime
    return None


def validate_upload(data: bytes, doc_type: str, max_pages: int) -> IntakeResult:
    if not data:
        raise IntakeError("empty_file", "The file is empty")
    mime = sniff(data)
    if mime is None:
        raise IntakeError("unsupported_type", "Only PDF, PNG and JPEG files are accepted (checked by content, not extension)")
    wants_image = doc_type in IMAGE_DOC_TYPES
    if wants_image and mime == "application/pdf":
        raise IntakeError("wrong_type", "Photographs must be uploaded as PNG or JPEG")
    if not wants_image and mime != "application/pdf":
        raise IntakeError("wrong_type", "This document must be uploaded as a PDF")
    if mime == "application/pdf":
        try:
            with pikepdf.open(io.BytesIO(data)) as pdf:
                pages = len(pdf.pages)
        except pikepdf.PasswordError:
            raise IntakeError("encrypted_pdf", "Password-protected PDFs cannot be checked; upload an unprotected copy") from None
        except Exception:
            raise IntakeError("malformed_pdf", "The PDF could not be parsed safely") from None
        if pages < 1:
            raise IntakeError("malformed_pdf", "The PDF has no pages")
        if pages > max_pages:
            raise IntakeError("too_many_pages", f"PDFs are limited to {max_pages} pages")
        return IntakeResult(mime, pages)
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
    except (Image.DecompressionBombError, Exception):
        raise IntakeError("malformed_image", "The image could not be read safely") from None
    if w < 64 or h < 64:
        raise IntakeError("image_too_small", "The photograph is too small to assess")
    return IntakeResult(mime, 1)
