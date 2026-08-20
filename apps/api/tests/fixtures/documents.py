"""Builders for the fixture documents. Every file stays well under a few hundred KB."""

from __future__ import annotations

import io
from pathlib import Path

import pillow_heif
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Registers the HEIF plugin for both reading and writing the .heic fixture.
pillow_heif.register_heif_opener()

PAGE_WIDTH, PAGE_HEIGHT = letter

BODY_LINE = "the quick brown fox jumps over the lazy dog and keeps running"


def _photo(width: int = 240, height: int = 180) -> ImageReader:
    """A small gradient bitmap standing in for a photograph or scan."""
    image = Image.new("RGB", (width, height))
    image.putdata(
        [((x * 7) % 256, (y * 5) % 256, 128) for y in range(height) for x in range(width)]
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


def _write_paragraph(pdf: canvas.Canvas, x: float, top: float, lines: int, width: int) -> None:
    pdf.setFont("Helvetica", 10)
    y = top
    for index in range(lines):
        pdf.drawString(x, y, f"{index:02d} {BODY_LINE}"[:width])
        y -= 13


def text_layer_page(pdf: canvas.Canvas) -> None:
    """A plain single-column page: the text-layer path."""
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, PAGE_HEIGHT - 72, "A Very Ordinary Report")
    _write_paragraph(pdf, 72, PAGE_HEIGHT - 110, lines=30, width=90)


def scanned_page(pdf: canvas.Canvas) -> None:
    """A page that is only a bitmap: no text layer at all, so the vision path."""
    pdf.drawImage(_photo(480, 620), 72, 100, width=460, height=600)


def two_column_page(pdf: canvas.Canvas) -> None:
    """Two text columns with a clear gutter: the vision path."""
    _write_paragraph(pdf, 60, PAGE_HEIGHT - 80, lines=40, width=42)
    _write_paragraph(pdf, 330, PAGE_HEIGHT - 80, lines=40, width=42)


def table_page(pdf: canvas.Canvas) -> None:
    """A grid of widely separated cells: the vision path."""
    pdf.setFont("Helvetica", 10)
    y = PAGE_HEIGHT - 80
    for row in range(24):
        for column, x in enumerate((72, 220, 370, 500)):
            pdf.drawString(x, y, f"r{row}c{column}")
        y -= 16


def build_text_layer_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    text_layer_page(pdf)
    pdf.showPage()
    pdf.save()
    return path


def build_scanned_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    scanned_page(pdf)
    pdf.showPage()
    pdf.save()
    return path


def build_two_column_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    two_column_page(pdf)
    pdf.showPage()
    pdf.save()
    return path


def build_table_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    table_page(pdf)
    pdf.showPage()
    pdf.save()
    return path


def build_mixed_pdf(path: Path) -> Path:
    """Three pages: text layer, scan, two columns."""
    pdf = canvas.Canvas(str(path), pagesize=letter)
    for page in (text_layer_page, scanned_page, two_column_page):
        page(pdf)
        pdf.showPage()
    pdf.save()
    return path


def build_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 4)
    return path


def build_image(path: Path, image_format: str, size: tuple[int, int] = (320, 240)) -> Path:
    image = Image.new("RGB", size)
    width, height = size
    image.putdata(
        [((x * 3) % 256, (y * 9) % 256, 200) for y in range(height) for x in range(width)]
    )
    image.save(path, format=image_format)
    return path


def build_rotated_jpeg(path: Path, size: tuple[int, int] = (400, 200)) -> Path:
    """A landscape JPEG tagged as needing a 90 degree rotation (EXIF orientation 6)."""
    image = Image.new("RGB", size, (10, 120, 200))
    exif = image.getexif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)
    return path
