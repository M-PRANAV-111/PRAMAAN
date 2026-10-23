"""Harder synthetic variants used by the AI evaluation and the grounding tests: unusual labels and layouts, low
resolution scans, rotated pages and handwriting-style date fields. All pages carry the SYNTHETIC stamp.

Each variant prints the same facts as the plain generator would, so the expected value of every field is known.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader

from .generator import FONT_PATH, H, Inst, Page, W, fmt, rasterize

# Script-style fonts, tried in order; the first that exists is used for "handwritten" dates.
_SCRIPT_FONTS = [
    r"C:\Windows\Fonts\Inkfree.ttf", r"C:\Windows\Fonts\segoesc.ttf", r"C:\Windows\Fonts\SCRIPTBL.TTF",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", FONT_PATH,
]


def _script_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _SCRIPT_FONTS:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _table_row(p: Page, label: str, value: str, x_value: float = 300) -> None:
    p.c.setFont("Helvetica", 11)
    p.c.drawString(40, p.y, label)
    p.c.drawString(x_value, p.y, value)
    p.c.line(36, p.y - 5, W - 36, p.y - 5)
    p.y -= 20


def fire_noc_variant(kind: str, inst: Inst, ref: str, issue: date, valid_to: date) -> bytes:
    """kind: ``expiry_label`` ("Expiry Date" instead of "Valid Upto") or ``two_column`` (label and value far apart)."""
    p = Page("FIRE SAFETY NO OBJECTION CERTIFICATE", "State Fire Services (synthetic issuer SYN-FIRE-TS)", issue)
    if kind == "expiry_label":
        p.label_value("Certificate No.", ref)
        p.label_value("Premises of", inst.name)
        p.label_value("Permanent Id", inst.pid)
        p.label_value("Issued", fmt(issue))
        p.label_value("Expiry Date", fmt(valid_to))
    elif kind == "two_column":
        for label, value in [("Certificate No.", ref), ("Premises of", inst.name), ("Permanent Id", inst.pid),
                             ("Date of Issue", fmt(issue)), ("Valid Upto", fmt(valid_to))]:
            _table_row(p, label, value)
    else:
        raise ValueError(kind)
    p.y -= 10
    p.line("Fire fighting installations were inspected and found satisfactory (synthetic).", gap=15)
    return p.done()


def affidavit_variant(kind: str, inst: Inst, ay: str, intake: int, faculty: int, signed: date) -> bytes:
    """kind: ``intake_label`` ("Intake proposed (seats)") or ``two_column`` (table form)."""
    p = Page("AFFIDAVIT (FORMAT FOR EXTENSION OF APPROVAL)", "On non-judicial stamp paper \u2014 synthetic replica", signed)
    p.line("I, the Chairman of the Trust/Society, do hereby solemnly affirm and state that:", gap=22)
    if kind == "intake_label":
        p.label_value("Name of Institution", inst.name)
        p.label_value("Permanent Id", inst.pid)
        p.label_value("Academic Year", ay)
        p.label_value("Intake proposed (seats)", str(intake))
        p.label_value("Number of Regular Faculty", str(faculty))
        p.label_value("Date of Affidavit", fmt(signed))
    elif kind == "two_column":
        for label, value in [("Name of Institution", inst.name), ("Permanent Id", inst.pid), ("Academic Year", ay),
                             ("Total Intake Sought", str(intake)), ("Number of Regular Faculty", str(faculty)),
                             ("Date of Affidavit", fmt(signed))]:
            _table_row(p, label, value)
    else:
        raise ValueError(kind)
    return p.done()


def handwritten_date_noc(inst: Inst, ref: str, issue: date, valid_to: date) -> bytes:
    """A fire NOC whose validity date is drawn in a script font, then scanned (image only)."""
    p = Page("FIRE SAFETY NO OBJECTION CERTIFICATE", "State Fire Services (synthetic issuer SYN-FIRE-TS)", issue)
    p.label_value("Certificate No.", ref)
    p.label_value("Permanent Id", inst.pid)
    p.label_value("Date of Issue", fmt(issue))
    p.c.setFont("Helvetica", 11)
    p.c.drawString(40, p.y, "Valid Upto:")
    scale = 8
    image = Image.new("RGB", (150 * scale, 22 * scale), "white")
    ImageDraw.Draw(image).text((0, 0), fmt(valid_to), fill=(20, 30, 90), font=_script_font(int(15 * scale)))
    p.c.drawImage(ImageReader(image), 40 + p.c.stringWidth("Valid Upto: ", "Helvetica", 11), p.y - 6, width=150, height=22)
    p.y -= 24
    return rasterize(p.done(), dpi=200)


def low_res_scan(pdf_bytes: bytes, dpi: int = 90) -> bytes:
    """Image-only copy at a low resolution (forces OCR, which gets harder as the dpi falls)."""
    return rasterize(pdf_bytes, dpi=dpi)


def rotated_scan(pdf_bytes: bytes, degrees: int = 90, dpi: int = 150) -> bytes:
    """Image-only copy turned by ``degrees`` (a sideways scan)."""
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas
    pdf = pdfium.PdfDocument(pdf_bytes)
    image = pdf[0].render(scale=dpi / 72).to_pil().convert("L").rotate(degrees, expand=True)
    pdf.close()
    out = io.BytesIO()
    w, h = (H, W) if degrees % 180 else (W, H)
    c = canvas.Canvas(out, pagesize=(w, h))
    c.setProducer("PRAMAAN synthetic scanner")
    c.drawImage(ImageReader(image), 0, 0, width=w, height=h)
    c.showPage()
    c.save()
    return out.getvalue()
