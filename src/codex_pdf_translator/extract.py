from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

from .jsonio import write_json


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return value.strip("-._") or "document"


def clean_text(value: str) -> str:
    lines = [line.strip() for line in value.replace("\r", "\n").split("\n")]
    kept = [line for line in lines if line]
    return "\n".join(kept).strip()


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    doc = fitz.open(str(pdf_path))
    pages: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []

    for page_index, page in enumerate(doc):
        rect = page.rect
        pages.append(
            {
                "index": page_index,
                "number": page_index + 1,
                "width": round(rect.width, 2),
                "height": round(rect.height, 2),
            }
        )
        text_blocks = page.get_text("blocks", sort=True)
        text_index = 0
        for block in text_blocks:
            x0, y0, x1, y1, text, _block_no, block_type = block[:7]
            if block_type != 0:
                continue
            text = clean_text(text)
            if not text:
                continue
            segments.append(
                {
                    "id": f"p{page_index + 1:04d}-b{text_index:03d}",
                    "page_index": page_index,
                    "page_number": page_index + 1,
                    "block_index": text_index,
                    "bbox": [round(float(v), 2) for v in (x0, y0, x1, y1)],
                    "source": text,
                }
            )
            text_index += 1

    return {
        "source_pdf_name": pdf_path.name,
        "page_count": len(pages),
        "pages": pages,
        "segments": segments,
    }


def chunk_segments(segments: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    for segment in segments:
        segment_chars = len(segment["source"])
        if current and current_chars + segment_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += segment_chars

    if current:
        chunks.append(current)
    return chunks


def prepare_run(
    pdf_path: Path,
    workdir: Path | None,
    source_lang: str,
    target_lang: str,
    chunk_chars: int,
    force: bool = False,
) -> Path:
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    if workdir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        workdir = Path("runs") / f"{slugify(pdf_path.stem)}-{stamp}"
    workdir = workdir.expanduser().resolve()

    if workdir.exists() and any(workdir.iterdir()):
        if not force:
            raise FileExistsError(f"{workdir} already exists; pass --force to reuse it")
        for child_name in [
            "chunks",
            "translations",
            "output",
            "manifest.json",
            "source.pdf",
            "CODEX_TASK.md",
        ]:
            child = workdir / child_name
            if child.is_dir():
                shutil.rmtree(child)
            elif child.exists():
                child.unlink()

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "chunks").mkdir(exist_ok=True)
    (workdir / "translations").mkdir(exist_ok=True)
    (workdir / "output").mkdir(exist_ok=True)

    source_copy = workdir / "source.pdf"
    shutil.copyfile(pdf_path, source_copy)

    extracted = extract_pdf(pdf_path)
    chunks = chunk_segments(extracted["segments"], chunk_chars)
    manifest = {
        **extracted,
        "source_pdf": str(source_copy),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "chunk_chars": chunk_chars,
        "chunk_count": len(chunks),
    }
    write_json(workdir / "manifest.json", manifest)

    for index, chunk in enumerate(chunks, start=1):
        chunk_payload = {
            "chunk_id": index,
            "chunk_count": len(chunks),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "segments": [
                {
                    "id": segment["id"],
                    "page_number": segment["page_number"],
                    "source": segment["source"],
                }
                for segment in chunk
            ],
        }
        write_json(workdir / "chunks" / f"chunk_{index:04d}.json", chunk_payload)

    task = f"""# Codex PDF Translation Run

Source: `{pdf_path}`
Run directory: `{workdir}`
Source language: `{source_lang}`
Target language: `{target_lang}`

Use:

```bash
codex-pdf-translate translate "{workdir}"
codex-pdf-translate merge "{workdir}"
codex-pdf-translate render "{workdir}" --mode bilingual
```

The `translate` command calls Codex CLI once per chunk and writes strict JSON files into
`translations/`. No OpenAI API key is required by this project; it relies on the local
Codex CLI login.
"""
    (workdir / "CODEX_TASK.md").write_text(task, encoding="utf-8")
    return workdir
