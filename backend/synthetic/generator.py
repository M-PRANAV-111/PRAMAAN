"""Synthetic document generator for demos, tests and the benchmark.

Every document is stamped "SYNTHETIC — NOT A REAL DOCUMENT" and uses fictional institutions,
identifiers and issuers. Layouts loosely follow publicly posted AICTE EoA letters and common
certificate formats; no real document text is reproduced.
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import cv2
import pikepdf
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

STAMP = "SYNTHETIC — NOT A REAL DOCUMENT · generated for PRAMAAN testing"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
W, H = A4


@dataclass
class Inst:
    name: str
    pid: str
    address: str = "Plot 7, Knowledge Park, Hyderabad, Telangana (synthetic)"


def fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


# ----------------------------------------------------------------------------- issuer keys
def issuer_keypair() -> tuple[str, str]:
    """Returns (private_pem, public_b64)."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, base64.b64encode(pub).decode()


def save_keys(path: Path, keys: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2))
    os.chmod(path, 0o600)


def signed_qr_text(private_pem: str, payload: dict) -> str:
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = key.sign(body)  # type: ignore[union-attr]
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"PRAMAAN-SQR1.{b64(body)}.{b64(sig)}"


def qr_image(text: str, px: int = 6) -> Image.Image:
    enc = cv2.QRCodeEncoder.create()
    m = enc.encode(text)
    m = cv2.resize(m, (m.shape[1] * px, m.shape[0] * px), interpolation=cv2.INTER_NEAREST)
    m = cv2.copyMakeBorder(m, 4 * px, 4 * px, 4 * px, 4 * px, cv2.BORDER_CONSTANT, value=255)
    return Image.fromarray(m).convert("RGB")


# ----------------------------------------------------------------------------- page helpers
class Page:
    def __init__(self, title: str, issuer_line: str, created: date):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.stamp = f"D:{created.strftime('%Y%m%d')}100000+05'30'"
        self.c.setCreator("PRAMAAN synthetic generator")
        self.c.setProducer("PRAMAAN synthetic generator")
        self.c.setTitle(title + " (SYNTHETIC)")
        self.y = H - 50
        self._watermark()
        self.c.setFillColor(HexColor("#b42318"))
        self.c.setFont("Helvetica-Bold", 7.5)
        self.c.drawString(40, H - 28, STAMP)
        self.c.setFillColor(HexColor("#111111"))
        self.c.setFont("Helvetica", 9)
        self.c.drawString(40, self.y, issuer_line)
        self.y -= 28
        self.c.setFont("Helvetica-Bold", 14)
        self.c.drawString(40, self.y, title)
        self.y -= 26
        self.c.setFont("Helvetica", 11)

    def _watermark(self) -> None:
        self.c.saveState()
        self.c.setFillColor(Color(0.85, 0.2, 0.2, alpha=0.07))
        self.c.setFont("Helvetica-Bold", 64)
        self.c.translate(W / 2, H / 2)
        self.c.rotate(35)
        self.c.drawCentredString(0, 0, "SYNTHETIC")
        self.c.restoreState()

    def line(self, text: str, gap: float = 18, bold: bool = False) -> float:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        self.c.drawString(40, self.y, text)
        y = self.y
        self.y -= gap
        return y

    def label_value(self, label: str, value: str, overlay_value: str | None = None) -> None:
        """Draws "label: value". With ``overlay_value`` the text layer keeps ``value`` but a raster patch
        showing ``overlay_value`` is painted over it — the signature of an overlay edit."""
        self.c.setFont("Helvetica", 11)
        prefix = f"{label}: "
        self.c.drawString(40, self.y, prefix + value)
        if overlay_value is not None:
            x = 40 + self.c.stringWidth(prefix, "Helvetica", 11)
            wv = self.c.stringWidth(value, "Helvetica", 11)
            wo = self.c.stringWidth(overlay_value, "Helvetica", 11)
            box_w = max(wv, wo) + 4
            scale = 8
            img = Image.new("RGB", (int(box_w * scale), int(15 * scale)), "white")
            font = ImageFont.truetype(FONT_PATH, int(11 * scale * 0.98))
            ImageDraw.Draw(img).text((0, int(2.2 * scale)), overlay_value, fill=(17, 17, 17), font=font)
            self.c.drawImage(ImageReader(img), x - 0.5, self.y - 3.5, width=box_w, height=15)
        self.y -= 18

    def qr(self, text: str, size: float = 120) -> None:
        self.c.drawImage(ImageReader(qr_image(text)), W - 40 - size, 60, width=size, height=size)
        self.c.setFont("Helvetica", 7)
        self.c.drawString(W - 40 - size, 52, "Signed QR — scan to verify (synthetic issuer)")

    def footer(self, text: str) -> None:
        self.c.setFont("Helvetica-Oblique", 8.5)
        self.c.drawString(40, 70, text)

    def done(self) -> bytes:
        self.c.showPage()
        self.c.save()
        # reportlab stamps "now"; rewrite metadata so the file looks issued on its own date.
        with pikepdf.open(io.BytesIO(self.buf.getvalue())) as pdf:
            pdf.docinfo["/CreationDate"] = self.stamp
            pdf.docinfo["/ModDate"] = self.stamp
            out = io.BytesIO()
            pdf.save(out, deterministic_id=True)
        return out.getvalue()


# ----------------------------------------------------------------------------- documents
def eoa_letter(inst: Inst, ay: str, intake: int, issue: date, printed: date | None = None,
               file_no: str = "SYN/EOA/2025-26/00417") -> bytes:
    p = Page("EXTENSION OF APPROVAL FOR THE ACADEMIC YEAR " + ay,
             "All India Council for Technical Education — format replica for testing (synthetic)", issue)
    p.c.setFont("Helvetica", 11)
    p.c.drawString(40, p.y, f"File No.: {file_no}")
    p.c.drawString(380, p.y, f"Date: {fmt(issue)}")
    p.y -= 26
    p.label_value("Permanent Id", inst.pid)
    p.label_value("Application Id", inst.pid.replace("SYN", "SYN-APP"))
    p.label_value("Name of the Institution", inst.name)
    p.label_value("Address", inst.address)
    p.y -= 8
    p.line("Programme  |  Course                              |  Intake", bold=True)
    per = intake // 3
    for course in ("Computer Science and Engineering", "Electronics and Communication Engg.", "Mechanical Engineering"):
        p.line(f"UG Engg.   |  {course:<36}|  {per}")
    p.y -= 6
    p.label_value("Total Approved Intake", str(intake))
    p.y -= 10
    p.line("The institution shall comply with the norms of the Approval Process Handbook.", gap=15)
    p.line("Course details may be verified on the council's website. Council records prevail.", gap=15)
    if printed:
        p.footer(f"Letter Printed On: {printed.strftime('%d %B %Y')}")
    return p.done()


def affidavit(inst: Inst, ay: str, intake: int, faculty: int, signed: date) -> bytes:
    p = Page("AFFIDAVIT (FORMAT FOR EXTENSION OF APPROVAL)", "On non-judicial stamp paper — synthetic replica", signed)
    p.line("I, the Chairman of the Trust/Society, do hereby solemnly affirm and state that:", gap=22)
    p.label_value("Name of Institution", inst.name)
    p.label_value("Permanent Id", inst.pid)
    p.label_value("Academic Year", ay)
    p.label_value("Total Intake Sought", str(intake))
    p.label_value("Number of Regular Faculty", str(faculty))
    p.label_value("Date of Affidavit", fmt(signed))
    p.y -= 10
    p.line("The information furnished is true and nothing material has been concealed.", gap=15)
    p.line("Deponent (synthetic signature)                      Notary (synthetic seal)", gap=15)
    return p.done()


def certificate(kind: str, inst: Inst, ref: str, issue: date, valid_to: date, area: int | None = None,
                qr_text: str | None = None, printed_valid_to: date | None = None) -> bytes:
    if kind == "fire_noc":
        title, issuer = "FIRE SAFETY NO OBJECTION CERTIFICATE", "State Fire Services (synthetic issuer SYN-FIRE-TS)"
    else:
        title, issuer = "STRUCTURAL STABILITY CERTIFICATE", "Licensed Structural Engineer (synthetic registry SYN-STRUCT)"
    p = Page(title, issuer, issue)
    p.label_value("Certificate No.", ref)
    p.label_value("Premises of", inst.name)
    p.label_value("Permanent Id", inst.pid)
    if area is not None:
        p.label_value("Built-up Area (sq.m)", str(area))
    p.label_value("Date of Issue", fmt(issue))
    p.label_value("Valid Upto", fmt(printed_valid_to or valid_to))
    p.y -= 10
    if kind == "fire_noc":
        p.line("Fire fighting installations were inspected and found satisfactory (synthetic).", gap=15)
    else:
        p.line("The structure is certified stable for academic use (synthetic).", gap=15)
    if qr_text:
        p.qr(qr_text)
    return p.done()


def faculty_summary(inst: Inst, ay: str, faculty: int, students: int, intake: int, faculty_overlay: int | None = None) -> bytes:
    p = Page("FACULTY AND STUDENT STRENGTH SUMMARY", "Institution declaration — synthetic", date(2026, 1, 10))
    p.label_value("Name of Institution", inst.name)
    p.label_value("Permanent Id", inst.pid)
    p.label_value("Academic Year", ay)
    p.label_value("Number of Regular Faculty", str(faculty), None if faculty_overlay is None else str(faculty_overlay))
    p.label_value("Total Student Strength", str(students))
    p.label_value("Total Intake", str(intake))
    return p.done()


def rasterize(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    """Turn a PDF into an image-only PDF (simulates a scanned copy; forces the OCR path)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    img = pdf[0].render(scale=dpi / 72).to_pil().convert("L")
    pdf.close()
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    c.setProducer("PRAMAAN synthetic scanner")
    c.drawImage(ImageReader(img), 0, 0, width=W, height=H)
    c.showPage()
    c.save()
    return out.getvalue()


def incremental_edit(pdf_bytes: bytes) -> bytes:
    """Append an incremental revision (metadata change) — a legitimate-looking later save."""
    writer = PdfWriter(io.BytesIO(pdf_bytes), incremental=True)
    writer.add_metadata({"/ModDate": "D:20260915120000+05'30'"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def lab_photo(seed: int, size: tuple[int, int] = (960, 640)) -> bytes:
    """Procedurally drawn computer-lab scene (no real photograph)."""
    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size, (232, 228, 220))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(h * 0.62), w, h], fill=(198, 186, 168))
    d.rectangle([40, 40, w - 40, 170], fill=(250, 250, 248), outline=(150, 150, 150), width=3)
    for row in range(3):
        y = int(h * 0.42) + row * 70
        for col in range(6):
            x = 60 + col * (w - 120) // 6 + rnd.randint(-6, 6)
            d.rectangle([x, y - 46, x + 70, y], fill=(30, 34, 44))
            d.rectangle([x + 4, y - 42, x + 66, y - 6], fill=(rnd.randint(60, 120), rnd.randint(110, 170), 210))
            d.rectangle([x - 12, y, x + 92, y + 14], fill=(120, 84, 52))
    d.text((60, 70), f"COMPUTER LAB {rnd.randint(1, 9)} — SYNTHETIC", fill=(40, 40, 40),
           font=ImageFont.truetype(FONT_PATH, 34))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def reencode_jpeg(png: bytes, quality: int = 82, scale: float = 0.9) -> bytes:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((int(img.width * scale), int(img.height * scale)))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def pdf_has_stamp(pdf_bytes: bytes) -> bool:
    return "SYNTHETIC" in (PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text() or "")

