from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from .jsonio import read_json
from .render import is_heading, should_skip_paper_segment, wrap_text


@dataclass
class Asset:
    page_index: int
    kind: str
    path: Path
    bbox: tuple[float, float, float, float]


PROTECTED_TERMS = {
    "FL",
    "SSFL",
    "SSFOD",
    "IID",
    "non-IID",
    "FedAvg",
    "FedProx",
    "FedAvgM",
    "FedCurv",
    "FedMA",
    "FedDF",
    "FedFocal",
    "FedWAvg",
    "STAC",
    "VOC",
    "COCO",
    "Faster R-CNN",
    "ResNet",
    "YOLO",
    "GDPR",
    "CCPA",
    "DynamoFL",
    "KAIST",
    "The Wharton School",
    "NeurIPS",
    "arXiv",
}


def markdown_escape(text: str) -> str:
    return text.replace("\u00a0", " ").strip()


def normalize_translation(source: str, target: str, in_references: bool = False) -> str:
    if in_references:
        return source.strip()

    text = target.strip()
    replacements = {
        "バックボーン": "backbone",
        "ネック": "neck",
        "ヘッド": "head",
        "サーバー": "server",
        "クライアント": "client",
        "教師": "teacher",
        "生徒": "student",
        "擬似ラベル": "pseudo label",
        "物体検出": "object detection",
    }
    for jp, en in replacements.items():
        if en in source:
            text = text.replace(jp, en)

    for term in sorted(PROTECTED_TERMS, key=len, reverse=True):
        if term in source and term not in text:
            compact = term.replace(" ", "")
            if compact in text:
                text = text.replace(compact, term)

    if source.startswith("Table"):
        text = re.sub(r"^Table\s+", "表", text)
    if source.startswith("Figure"):
        text = re.sub(r"^Figure\s+", "図", text)
    return text


def source_markdown_role(source: str, target: str) -> str:
    source = source.strip()
    target = target.strip()
    compact_source = compact_heading(source)
    if source.lower() in {"abstract", "references", "acknowledgments"}:
        return "heading"
    if starts_appendix(source):
        return "heading"
    if target in {"要旨", "参考文献", "謝辞"}:
        return "heading"
    if re.match(r"^\d+(\.\d+)*\s+", compact_source):
        return "heading"
    if source.startswith(("Figure", "Table")) or target.startswith(("図", "表")):
        return "caption"
    return "body"


def compact_heading(text: str) -> str:
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def starts_appendix(source: str) -> bool:
    return bool(re.match(r"^[A-Z](\.\d+)?\s+[A-Z]", compact_heading(source)))


def should_skip_markdown_segment(segment: dict[str, Any], target: str) -> bool:
    source = segment["source"].strip()
    lower_source = source.lower()
    if "conference on neural information processing systems" in lower_source:
        return True
    return should_skip_paper_segment(segment, target)


def rect_tuple(rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def rect_area(rect: fitz.Rect) -> float:
    return max(0.0, rect.width) * max(0.0, rect.height)


def close_enough(left: fitz.Rect, right: fitz.Rect, margin: float) -> bool:
    expanded = fitz.Rect(left.x0 - margin, left.y0 - margin, left.x1 + margin, left.y1 + margin)
    return bool(expanded.intersects(right))


def merge_rects(rects: list[fitz.Rect], margin: float = 10.0) -> list[fitz.Rect]:
    merged: list[fitz.Rect] = []
    for rect in rects:
        if rect.is_empty or rect.width < 4 or rect.height < 4:
            continue
        current = fitz.Rect(rect)
        changed = True
        while changed:
            changed = False
            remaining: list[fitz.Rect] = []
            for other in merged:
                if close_enough(current, other, margin):
                    current.include_rect(other)
                    changed = True
                else:
                    remaining.append(other)
            merged = remaining
        merged.append(current)
    return sorted(merged, key=lambda item: (item.y0, item.x0))


def page_asset_rects(page: fitz.Page) -> list[tuple[str, fitz.Rect]]:
    page_area = page.rect.width * page.rect.height
    rects: list[tuple[str, fitz.Rect]] = []

    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") == 1:
            rect = fitz.Rect(block["bbox"])
            if rect_area(rect) > page_area * 0.002:
                rects.append(("figure", rect))

    try:
        tables = page.find_tables().tables
    except Exception:
        tables = []
    for table in tables:
        rect = fitz.Rect(table.bbox)
        if rect_area(rect) > page_area * 0.002:
            rects.append(("table", rect))

    drawing_rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect", fitz.EMPTY_RECT()))
        if rect_area(rect) > page_area * 0.001 and rect.width > 20 and rect.height > 12:
            drawing_rects.append(rect)
    for rect in merge_rects(drawing_rects, margin=14.0):
        if rect_area(rect) > page_area * 0.012:
            rects.append(("figure", rect))

    grouped: list[tuple[str, fitz.Rect]] = []
    for kind in ["figure", "table"]:
        for rect in merge_rects([rect for rect_kind, rect in rects if rect_kind == kind], margin=18.0):
            if rect_area(rect) > page_area * 0.006:
                grouped.append((kind, rect))

    final: list[tuple[str, fitz.Rect]] = []
    for kind, rect in sorted(grouped, key=lambda item: (item[1].y0, item[1].x0)):
        merged = False
        for index, (existing_kind, existing_rect) in enumerate(final):
            overlap = rect_area(rect & existing_rect)
            if overlap / max(1.0, min(rect_area(rect), rect_area(existing_rect))) > 0.25:
                combined = fitz.Rect(existing_rect)
                combined.include_rect(rect)
                combined_kind = "figure" if "figure" in {kind, existing_kind} else "table"
                final[index] = (combined_kind, combined)
                merged = True
                break
        if not merged:
            final.append((kind, rect))
    return sorted(final, key=lambda item: (item[1].y0, item[1].x0))


def extract_assets(run_dir: Path, output_dir: Path) -> list[Asset]:
    source_doc = fitz.open(str(run_dir / "source.pdf"))
    assets_dir = output_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    assets: list[Asset] = []
    for page_index, page in enumerate(source_doc):
        seen: list[fitz.Rect] = []
        asset_no = 1
        for kind, rect in page_asset_rects(page):
            padded = fitz.Rect(
                max(0, rect.x0 - 8),
                max(0, rect.y0 - 8),
                min(page.rect.width, rect.x1 + 8),
                min(page.rect.height, rect.y1 + 8),
            )
            if any(rect_area(padded & prior) / max(1.0, rect_area(padded)) > 0.85 for prior in seen):
                continue
            seen.append(padded)
            filename = f"page-{page_index + 1:02d}-{kind}-{asset_no:02d}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=padded, alpha=False)
            path = assets_dir / filename
            pix.save(path)
            assets.append(Asset(page_index, kind, path, rect_tuple(padded)))
            asset_no += 1
    return assets


def segment_is_visual_label(segment: dict[str, Any], source: str) -> bool:
    text = source.strip()
    if not text:
        return True
    if source_markdown_role(source, text) == "caption":
        return False
    if source_markdown_role(source, text) == "heading":
        return False
    letters = sum(char.isalpha() for char in text)
    digits = sum(char.isdigit() for char in text)
    symbols = sum(char in "[](),.;:=+-/%❄🔥" for char in text)
    length = max(1, len(text))
    x0, y0, x1, y1 = segment["bbox"]
    width = x1 - x0
    height = y1 - y0
    if letters < 8 and (digits + symbols) / length > 0.35:
        return True
    if len(text) < 24 and width < 130 and height < 28:
        return True
    return False


def segment_inside_asset(segment: dict[str, Any], assets: list[Asset]) -> bool:
    x0, y0, x1, y1 = segment["bbox"]
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    for asset in assets:
        ax0, ay0, ax1, ay1 = asset.bbox
        if ax0 <= center_x <= ax1 and ay0 <= center_y <= ay1:
            return True
    return False


def segments_by_page(manifest: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = {}
    for segment in manifest["segments"]:
        pages.setdefault(segment["page_index"], []).append(segment)
    for page_segments in pages.values():
        page_segments.sort(key=lambda item: item["block_index"])
    return pages


def export_markdown(run_dir: Path, output_dir: Path, filename: str = "paper-ja.md") -> Path:
    run_dir = run_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_json(run_dir / "manifest.json")
    translations = read_json(run_dir / "translations.json")["translations"]
    assets = extract_assets(run_dir, output_dir)
    assets_by_page: dict[int, list[Asset]] = {}
    for asset in assets:
        assets_by_page.setdefault(asset.page_index, []).append(asset)

    lines: list[str] = []
    title = compact_heading(
        normalize_translation(
            manifest["segments"][0]["source"],
            translations.get(manifest["segments"][0]["id"], manifest["segments"][0]["source"]),
        )
    )
    lines.extend([f"# {markdown_escape(title)}", ""])

    in_references = False
    emitted_assets: set[Path] = set()

    first_segment_id = manifest["segments"][0]["id"] if manifest["segments"] else ""
    page_segments_map = segments_by_page(manifest)

    for page in manifest["pages"]:
        page_index = page["index"]
        for segment in page_segments_map.get(page_index, []):
            if segment["id"] == first_segment_id:
                continue
            source = segment["source"].strip()
            role = source_markdown_role(source, translations.get(segment["id"], source))
            if should_skip_markdown_segment(segment, translations.get(segment["id"], source)):
                continue
            if segment_is_visual_label(segment, source):
                continue
            if role != "caption" and segment_inside_asset(segment, assets_by_page.get(page_index, [])):
                continue

            if source.lower() == "references" or translations.get(segment["id"], "").strip() == "参考文献":
                in_references = True
            elif in_references and starts_appendix(source):
                in_references = False

            target = normalize_translation(
                source,
                translations.get(segment["id"], source),
                in_references=in_references and role != "heading",
            )
            target = markdown_escape(target)
            if not target:
                continue

            if role == "heading":
                target = compact_heading(target)
                heading_level = (
                    "##"
                    if re.match(r"^\d+(\.\d+)*\s+", compact_heading(source))
                    or target in {"要旨", "参考文献"}
                    else "###"
                )
                lines.extend([f"{heading_level} {target}", ""])
            elif role == "caption":
                lines.extend([f"> {target}", ""])
            else:
                paragraph = " ".join(part.strip() for part in target.splitlines() if part.strip())
                lines.extend([paragraph, ""])

        for asset in assets_by_page.get(page_index, []):
            if asset.path in emitted_assets:
                continue
            emitted_assets.add(asset.path)
            rel = asset.path.relative_to(output_dir)
            label = "図表" if asset.kind == "figure" else "表"
            lines.extend([f"![{label}: page {page_index + 1}]({rel.as_posix()})", ""])

    output_path = output_dir / filename
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path
