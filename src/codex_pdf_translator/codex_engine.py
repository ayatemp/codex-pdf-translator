from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .jsonio import read_json, write_json


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "target": {"type": "string", "minLength": 1},
                },
                "required": ["id", "target"],
            },
        }
    },
    "required": ["translations"],
}


def build_prompt(chunk: dict[str, Any]) -> str:
    source_lang = chunk["source_lang"]
    target_lang = chunk["target_lang"]
    source_json = json.dumps(chunk["segments"], ensure_ascii=False, indent=2)
    return f"""You are translating academic PDF text extracted from layout blocks.

Translate every segment from {source_lang} to {target_lang}.

Rules:
- Return JSON only, matching the provided output schema.
- Preserve each `id` exactly.
- Translate technical terms accurately and naturally for an academic paper.
- Keep formulas, symbols, citation markers, section numbers, URLs, and references intact.
- Do not summarize, omit, merge, or split segments.
- If a segment is already target-language text, copy it naturally.
- Every `target` value must be non-empty. If text should not be translated, copy it.

Segments:
{source_json}
"""


def validate_translation(chunk: dict[str, Any], translated: dict[str, Any]) -> None:
    expected = [segment["id"] for segment in chunk["segments"]]
    actual = [segment["id"] for segment in translated.get("translations", [])]
    if expected != actual:
        raise ValueError(
            "translated IDs do not match source IDs: "
            f"expected {expected[:5]}... got {actual[:5]}..."
        )
    for item in translated["translations"]:
        if not isinstance(item.get("target"), str) or not item["target"].strip():
            raise ValueError(f"empty translation for {item.get('id')}")


def codex_available(codex_bin: str) -> bool:
    return shutil.which(codex_bin) is not None


def translate_chunk(
    run_dir: Path,
    chunk_path: Path,
    output_path: Path,
    codex_bin: str = "codex",
    model: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    attempts: int = 2,
) -> None:
    if output_path.exists() and not force:
        try:
            translated = read_json(output_path)
            validate_translation(read_json(chunk_path), translated)
            return
        except Exception:
            output_path.replace(output_path.with_suffix(".invalid.json"))

    if not codex_available(codex_bin):
        raise RuntimeError(f"Codex CLI not found: {codex_bin}")

    chunk = read_json(chunk_path)
    prompt = build_prompt(chunk)
    schema_path = run_dir / ".codex_translation_schema.json"
    write_json(schema_path, OUTPUT_SCHEMA)

    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "-C",
        str(run_dir),
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
    ]
    if model:
        cmd.extend(["-m", model])
    cmd.append("-")

    if dry_run:
        print(" ".join(cmd))
        return

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            last_error = RuntimeError(result.stdout)
        else:
            try:
                translated = read_json(output_path)
                validate_translation(chunk, translated)
                return
            except Exception as exc:
                last_error = exc
                if output_path.exists():
                    output_path.replace(output_path.with_suffix(f".attempt{attempt}.invalid.json"))

        log_path = output_path.with_suffix(f".attempt{attempt}.log")
        log_path.write_text(str(last_error), encoding="utf-8")

    raise RuntimeError(f"Codex failed for {chunk_path.name}; see {output_path.with_suffix('.attempt1.log')}")


def translate_run(
    run_dir: Path,
    codex_bin: str = "codex",
    model: str | None = None,
    start: int = 1,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    attempts: int = 2,
) -> list[Path]:
    run_dir = run_dir.expanduser().resolve()
    chunk_paths = sorted((run_dir / "chunks").glob("chunk_*.json"))
    selected = [path for path in chunk_paths if int(path.stem.split("_")[1]) >= start]
    if limit is not None:
        selected = selected[:limit]

    outputs: list[Path] = []
    for chunk_path in selected:
        output_path = run_dir / "translations" / chunk_path.name
        translate_chunk(
            run_dir=run_dir,
            chunk_path=chunk_path,
            output_path=output_path,
            codex_bin=codex_bin,
            model=model,
            force=force,
            dry_run=dry_run,
            attempts=attempts,
        )
        outputs.append(output_path)
    return outputs


def merge_translations(run_dir: Path) -> Path:
    run_dir = run_dir.expanduser().resolve()
    manifest = read_json(run_dir / "manifest.json")
    translations: dict[str, str] = {}

    for chunk_path in sorted((run_dir / "chunks").glob("chunk_*.json")):
        translated_path = run_dir / "translations" / chunk_path.name
        if not translated_path.exists():
            raise FileNotFoundError(f"missing translation: {translated_path}")
        chunk = read_json(chunk_path)
        translated = read_json(translated_path)
        validate_translation(chunk, translated)
        for item in translated["translations"]:
            translations[item["id"]] = item["target"]

    expected_ids = [segment["id"] for segment in manifest["segments"]]
    missing = [segment_id for segment_id in expected_ids if segment_id not in translations]
    if missing:
        raise ValueError(f"missing translations: {missing[:10]}")

    output_path = run_dir / "translations.json"
    write_json(
        output_path,
        {
            "source_pdf_name": manifest["source_pdf_name"],
            "source_lang": manifest["source_lang"],
            "target_lang": manifest["target_lang"],
            "translations": translations,
        },
    )
    return output_path
