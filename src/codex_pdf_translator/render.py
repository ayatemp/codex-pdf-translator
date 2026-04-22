from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from .jsonio import read_json

FONT_NAME = "HeiseiMin-W3"


def register_fonts() -> None:
    try:
        pdfmetrics.getFont(FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def wrap_text(text: str, width: float, font_name: str, font_size: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        tokens = paragraph.split(" ")
        if len(tokens) == 1:
            current = ""
            for char in paragraph:
                trial = current + char
                if current and pdfmetrics.stringWidth(trial, font_name, font_size) > width:
                    lines.append(current)
                    current = char
                else:
                    current = trial
            if current:
                lines.append(current)
            continue

        current = ""
        for token in tokens:
            trial = token if not current else f"{current} {token}"
            if current and pdfmetrics.stringWidth(trial, font_name, font_size) > width:
                lines.append(current)
                current = token
            else:
                current = trial
        if current:
            lines.append(current)
    return lines


def page_image_reader(doc: fitz.Document, page_index: int, zoom: float = 1.5) -> ImageReader:
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return ImageReader(BytesIO(pix.tobytes("png")))


def draw_image_fit(
    pdf: canvas.Canvas,
    image: ImageReader,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    image_width, image_height = image.getSize()
    scale = min(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    pdf.drawImage(
        image,
        x + (width - draw_width) / 2,
        y + (height - draw_height) / 2,
        draw_width,
        draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def draw_paragraphs(
    pdf: canvas.Canvas,
    paragraphs: list[str],
    x: float,
    top: float,
    width: float,
    bottom: float,
    page_size: tuple[float, float],
    font_size: float,
    leading: float | None = None,
) -> tuple[int, float]:
    leading = leading or font_size * 1.45
    y = top
    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        lines = wrap_text(paragraph, width, FONT_NAME, font_size)
        needed = max(1, len(lines)) * leading + leading * 0.5
        if y - needed < bottom:
            pdf.showPage()
            pdf.setFont(FONT_NAME, font_size)
            y = page_size[1] - 42
        for line in lines:
            pdf.drawString(x, y, line)
            y -= leading
        y -= leading * 0.45
        index += 1
    return index, y


def draw_text_box(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y_from_top: float,
    width: float,
    height: float,
    page_height: float,
    font_size: float,
) -> None:
    size = font_size
    line_sets: list[str] = []
    while size >= 5:
        line_sets = wrap_text(text, width - 4, FONT_NAME, size)
        if len(line_sets) * size * 1.25 <= height - 4:
            break
        size -= 0.5

    y = page_height - y_from_top - size - 2
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(x, page_height - y_from_top - height, width, height, stroke=0, fill=1)
    pdf.setFillColorRGB(0.05, 0.05, 0.05)
    pdf.setFont(FONT_NAME, size)
    for line in line_sets:
        if y < page_height - y_from_top - height + 2:
            break
        pdf.drawString(x + 2, y, line)
        y -= size * 1.25


def page_paragraphs(
    segments: list[dict[str, Any]],
    translations: dict[str, str],
    page_index: int,
    include_source: bool = False,
) -> list[str]:
    paragraphs: list[str] = []
    for segment in segments:
        if segment["page_index"] != page_index:
            continue
        target = translations.get(segment["id"], segment["source"])
        if include_source:
            paragraphs.append(segment["source"])
        paragraphs.append(target)
    return paragraphs


def render_translated(run_dir: Path, output_path: Path, font_size: float) -> Path:
    register_fonts()
    manifest = read_json(run_dir / "manifest.json")
    translations = read_json(run_dir / "translations.json")["translations"]
    page_size = A4
    pdf = canvas.Canvas(str(output_path), pagesize=page_size)
    pdf.setTitle(f"Translated - {manifest['source_pdf_name']}")
    pdf.setFont(FONT_NAME, font_size)

    margin = 42
    for page in manifest["pages"]:
        paragraphs = page_paragraphs(manifest["segments"], translations, page["index"])
        draw_paragraphs(
            pdf,
            paragraphs,
            margin,
            page_size[1] - margin,
            page_size[0] - margin * 2,
            margin,
            page_size,
            font_size,
        )
        pdf.showPage()
        pdf.setFont(FONT_NAME, font_size)
    pdf.save()
    return output_path


def render_bilingual(run_dir: Path, output_path: Path, font_size: float) -> Path:
    register_fonts()
    manifest = read_json(run_dir / "manifest.json")
    translations = read_json(run_dir / "translations.json")["translations"]
    source_doc = fitz.open(str(run_dir / "source.pdf"))
    page_size = landscape(A4)
    pdf = canvas.Canvas(str(output_path), pagesize=page_size)
    pdf.setTitle(f"Bilingual - {manifest['source_pdf_name']}")

    margin = 30
    gutter = 24
    left_width = (page_size[0] - margin * 2 - gutter) / 2
    right_width = left_width
    usable_height = page_size[1] - margin * 2

    for page in manifest["pages"]:
        image = page_image_reader(source_doc, page["index"])
        draw_image_fit(pdf, image, margin, margin, left_width, usable_height)
        pdf.setFont(FONT_NAME, font_size)
        paragraphs = page_paragraphs(manifest["segments"], translations, page["index"])
        draw_paragraphs(
            pdf,
            paragraphs,
            margin + left_width + gutter,
            page_size[1] - margin,
            right_width,
            margin,
            page_size,
            font_size,
        )
        pdf.showPage()
    pdf.save()
    return output_path


def render_overlay(run_dir: Path, output_path: Path, font_size: float) -> Path:
    register_fonts()
    manifest = read_json(run_dir / "manifest.json")
    translations = read_json(run_dir / "translations.json")["translations"]
    source_doc = fitz.open(str(run_dir / "source.pdf"))
    first = manifest["pages"][0]
    pdf = canvas.Canvas(str(output_path), pagesize=(first["width"], first["height"]))
    pdf.setTitle(f"Overlay translated - {manifest['source_pdf_name']}")

    for page in manifest["pages"]:
        pdf.setPageSize((page["width"], page["height"]))
        image = page_image_reader(source_doc, page["index"], zoom=1.8)
        draw_image_fit(pdf, image, 0, 0, page["width"], page["height"])
        for segment in manifest["segments"]:
            if segment["page_index"] != page["index"]:
                continue
            x0, y0, x1, y1 = segment["bbox"]
            target = translations.get(segment["id"], segment["source"])
            draw_text_box(
                pdf,
                target,
                x0,
                y0,
                max(8, x1 - x0),
                max(8, y1 - y0),
                page["height"],
                font_size,
            )
        pdf.showPage()
    pdf.save()
    return output_path


def render_pdf(run_dir: Path, output_path: Path | None, mode: str, font_size: float = 9.0) -> Path:
    run_dir = run_dir.expanduser().resolve()
    if output_path is None:
        output_path = run_dir / "output" / f"{mode}.pdf"
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "translated":
        return render_translated(run_dir, output_path, font_size)
    if mode == "bilingual":
        return render_bilingual(run_dir, output_path, font_size)
    if mode == "overlay":
        return render_overlay(run_dir, output_path, font_size)
    raise ValueError(f"unknown mode: {mode}")
