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


def fill_rect_from_top(
    pdf: canvas.Canvas,
    x: float,
    y_from_top: float,
    width: float,
    height: float,
    page_height: float,
) -> None:
    pdf.rect(x, page_height - y_from_top - height, width, height, stroke=0, fill=1)


def is_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped in {"Abstract", "References", "Acknowledgments", "要旨", "参考文献"}:
        return True
    return bool(stripped[0].isdigit() and stripped[0] != "0" and len(stripped.splitlines()) <= 2)


def column_bands(page_segments: list[dict[str, Any]], page_width: float) -> dict[str, tuple[float, float]]:
    regular = [
        segment
        for segment in page_segments
        if segment["bbox"][2] - segment["bbox"][0] < page_width * 0.58
    ]
    left = [segment for segment in regular if (segment["bbox"][0] + segment["bbox"][2]) / 2 < page_width / 2]
    right = [segment for segment in regular if (segment["bbox"][0] + segment["bbox"][2]) / 2 >= page_width / 2]

    margin = max(28.0, page_width * 0.055)
    gutter = max(14.0, page_width * 0.025)
    fallback_width = (page_width - margin * 2 - gutter) / 2

    def band(items: list[dict[str, Any]], fallback_x: float, fallback_w: float) -> tuple[float, float]:
        if not items:
            return fallback_x, fallback_w
        x0 = max(margin, min(segment["bbox"][0] for segment in items) - 2)
        x1 = min(page_width - margin, max(segment["bbox"][2] for segment in items) + 2)
        if x1 - x0 < fallback_w * 0.75:
            return fallback_x, fallback_w
        return x0, x1 - x0

    return {
        "left": band(left, margin, fallback_width),
        "right": band(right, margin + fallback_width + gutter, fallback_width),
        "wide": (margin, page_width - margin * 2),
    }


def draw_reflowed_block(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y_from_top: float,
    width: float,
    page_height: float,
    font_size: float,
    bottom_margin: float,
) -> float:
    size = font_size + 1.0 if is_heading(text) else font_size
    leading = size * 1.38
    lines = wrap_text(text, width - 6, FONT_NAME, size)
    height = max(leading, len(lines) * leading) + leading * 0.45

    pdf.setFillColorRGB(1, 1, 1)
    fill_rect_from_top(pdf, x - 1, y_from_top - 1, width + 2, height + 2, page_height)
    pdf.setFillColorRGB(0.04, 0.04, 0.04)
    pdf.setFont(FONT_NAME, size)
    y = page_height - y_from_top - size
    for line in lines:
        pdf.drawString(x + 3, y, line)
        y -= leading
    return y_from_top + height


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


def should_skip_paper_segment(segment: dict[str, Any], target: str) -> bool:
    source = segment["source"].strip()
    stripped = target.strip()
    if not stripped:
        return True
    if stripped.isdigit() and segment["bbox"][1] > 680:
        return True
    lower_source = source.lower()
    lower_target = stripped.lower()
    repeated_headers = [
        "proceedings of",
        "published as a conference paper",
        "international conference on learning representations",
    ]
    if any(header in lower_source or header in lower_target for header in repeated_headers):
        return True
    if segment["page_index"] == 0 and segment["block_index"] <= 5:
        return False
    if is_heading(stripped) or stripped.startswith(("図", "表", "Figure", "Table")):
        return False

    source_digits = sum(char.isdigit() for char in source)
    source_letters = sum(char.isalpha() for char in source)
    source_symbols = sum(char in "[](),.;:=+-/%" for char in source)
    source_len = max(1, len(source))
    x0, y0, x1, y1 = segment["bbox"]
    width = x1 - x0
    height = y1 - y0

    if "[" in source and "]" in source and source_digits / source_len > 0.25:
        return True
    if source_digits / source_len > 0.42 and source_letters < 10:
        return True
    if source_symbols / source_len > 0.45 and source_letters < 14:
        return True
    if len(stripped) < 16 and width < 150 and height < 26:
        return True
    if len(stripped) < 34 and width < 90:
        return True
    return False


def classify_paper_block(segment: dict[str, Any], target: str, body_started: bool) -> str:
    stripped = target.strip()
    if not body_started and segment["page_index"] == 0:
        if segment["block_index"] <= 1 and len(stripped) <= 140:
            return "title"
        if segment["block_index"] <= 5:
            return "meta"
    if is_heading(stripped):
        return "heading"
    if stripped.startswith(("図", "表", "Figure", "Table")):
        return "caption"
    return "body"


def render_paper(run_dir: Path, output_path: Path, font_size: float) -> Path:
    register_fonts()
    manifest = read_json(run_dir / "manifest.json")
    translations = read_json(run_dir / "translations.json")["translations"]
    page_size = A4
    pdf = canvas.Canvas(str(output_path), pagesize=page_size)
    pdf.setTitle(f"Paper translation - {manifest['source_pdf_name']}")

    margin = 42
    full_width = page_size[0] - margin * 2
    column_width = full_width
    y = page_size[1] - margin
    page_number = 1
    body_started = False
    abstract_seen = False

    def new_page() -> None:
        nonlocal y, page_number
        pdf.setFont(FONT_NAME, 6.5)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawCentredString(page_size[0] / 2, 20, str(page_number))
        pdf.showPage()
        page_number += 1
        y = page_size[1] - margin
        pdf.setFillColorRGB(0.04, 0.04, 0.04)

    def current_x() -> float:
        return margin

    def advance_column() -> None:
        new_page()

    def draw_full(text: str, size: float, gap: float, centered: bool = False) -> None:
        nonlocal y
        leading = size * 1.35
        lines = wrap_text(text, full_width, FONT_NAME, size)
        needed = len(lines) * leading + gap
        if y - needed < margin:
            new_page()
        pdf.setFont(FONT_NAME, size)
        pdf.setFillColorRGB(0.04, 0.04, 0.04)
        for line in lines:
            if centered:
                pdf.drawCentredString(page_size[0] / 2, y, line)
            else:
                pdf.drawString(margin, y, line)
            y -= leading
        y -= gap

    def draw_column(text: str, size: float, gap: float) -> None:
        nonlocal y
        leading = size * 1.35
        lines = wrap_text(text, column_width, FONT_NAME, size)
        index = 0
        while index < len(lines):
            if y - leading < margin:
                advance_column()
            pdf.setFont(FONT_NAME, size)
            pdf.setFillColorRGB(0.04, 0.04, 0.04)
            pdf.drawString(current_x(), y, lines[index])
            y -= leading
            index += 1
        y -= gap

    ordered_segments = sorted(
        manifest["segments"],
        key=lambda item: (item["page_index"], item["block_index"]),
    )
    for segment in ordered_segments:
        target = translations.get(segment["id"], segment["source"]).strip()
        if should_skip_paper_segment(segment, target):
            continue

        role = classify_paper_block(segment, target, body_started)
        if (
            not body_started
            and abstract_seen
            and role == "heading"
            and (target.startswith("1") or target.startswith("1\n"))
        ):
            body_started = True
            y -= 6

        if not body_started:
            if target in {"要旨", "Abstract"}:
                abstract_seen = True
            if role == "title":
                draw_full(target, 13.5, 8, centered=True)
            elif role == "meta":
                draw_full(target, 7.5, 3, centered=True)
            elif role == "heading":
                draw_full(target, 9.0, 4, centered=False)
            elif role == "caption":
                continue
            elif not abstract_seen:
                continue
            else:
                draw_full(target, 7.7, 6, centered=False)
            continue

        if role == "heading":
            if y < margin + 45:
                advance_column()
            draw_column(target, 8.7, 5)
        elif role == "caption":
            draw_column(target, 6.7, 4)
        else:
            draw_column(target, font_size, 4.2)

    pdf.setFont(FONT_NAME, 6.5)
    pdf.setFillColorRGB(0.45, 0.45, 0.45)
    pdf.drawCentredString(page_size[0] / 2, 20, str(page_number))
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

        page_segments = [
            segment for segment in manifest["segments"] if segment["page_index"] == page["index"]
        ]

        # Remove source text first. Figures and raster content usually remain visible because
        # only the text boxes are covered.
        pdf.setFillColorRGB(1, 1, 1)
        for segment in page_segments:
            x0, y0, x1, y1 = segment["bbox"]
            pad = 1.4
            fill_rect_from_top(
                pdf,
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(page["width"], x1 + pad) - max(0, x0 - pad),
                min(page["height"], y1 + pad) - max(0, y0 - pad),
                page["height"],
            )

        bands = column_bands(page_segments, page["width"])
        top_margin = max(24.0, page["height"] * 0.035)
        bottom_margin = max(24.0, page["height"] * 0.04)
        cursors = {"left": top_margin, "right": top_margin, "wide": top_margin}

        for segment in page_segments:
            x0, y0, x1, y1 = segment["bbox"]
            target = translations.get(segment["id"], segment["source"])

            segment_width = x1 - x0
            center_x = (x0 + x1) / 2
            if segment_width >= page["width"] * 0.58 or y0 < page["height"] * 0.18:
                lane = "wide"
                x, width = bands["wide"]
                y_start = max(y0, cursors["wide"], cursors["left"], cursors["right"])
            elif center_x < page["width"] / 2:
                lane = "left"
                x, width = bands["left"]
                y_start = max(y0, cursors[lane])
            else:
                lane = "right"
                x, width = bands["right"]
                y_start = max(y0, cursors[lane])

            estimate_lines = wrap_text(target, width - 6, FONT_NAME, font_size)
            estimate_height = max(font_size * 1.38, len(estimate_lines) * font_size * 1.38)
            if y_start + estimate_height > page["height"] - bottom_margin:
                pdf.showPage()
                pdf.setPageSize((page["width"], page["height"]))
                pdf.setFillColorRGB(1, 1, 1)
                pdf.rect(0, 0, page["width"], page["height"], stroke=0, fill=1)
                pdf.setFillColorRGB(0.35, 0.35, 0.35)
                pdf.setFont(FONT_NAME, max(6.0, font_size - 1.0))
                pdf.drawString(
                    bands["wide"][0],
                    page["height"] - top_margin,
                    f"continued translation from source page {page['number']}",
                )
                cursors = {
                    "left": top_margin + font_size * 2,
                    "right": top_margin + font_size * 2,
                    "wide": top_margin + font_size * 2,
                }
                y_start = cursors["wide" if lane == "wide" else lane]

            y_after = draw_reflowed_block(
                pdf,
                target,
                x,
                y_start,
                width,
                page["height"],
                font_size,
                bottom_margin,
            )
            if lane == "wide":
                cursors = {"left": y_after + 3, "right": y_after + 3, "wide": y_after + 3}
            else:
                cursors[lane] = y_after + 3
                cursors["wide"] = max(cursors["wide"], min(cursors["left"], cursors["right"]))
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
    if mode == "paper":
        return render_paper(run_dir, output_path, font_size)
    if mode == "overlay":
        return render_overlay(run_dir, output_path, font_size)
    raise ValueError(f"unknown mode: {mode}")
