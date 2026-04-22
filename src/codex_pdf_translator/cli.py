from __future__ import annotations

import argparse
from pathlib import Path

from .codex_engine import merge_translations, translate_run, validate_translation
from .extract import prepare_run
from .jsonio import read_json
from .markdown_export import export_markdown
from .render import render_pdf


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-pdf-translate",
        description="Prepare PDF chunks, translate them through Codex CLI, and render translated PDFs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Extract text blocks from a PDF into a translation run.")
    prepare.add_argument("pdf", type=Path)
    prepare.add_argument("--workdir", type=Path)
    prepare.add_argument("--source-lang", default="English")
    prepare.add_argument("--target-lang", default="Japanese")
    prepare.add_argument("--chunk-chars", type=positive_int, default=6000)
    prepare.add_argument("--force", action="store_true")

    translate = sub.add_parser("translate", help="Translate run chunks by calling Codex CLI.")
    translate.add_argument("run_dir", type=Path)
    translate.add_argument("--codex-bin", default="codex")
    translate.add_argument("--model")
    translate.add_argument("--start", type=positive_int, default=1)
    translate.add_argument("--limit", type=positive_int)
    translate.add_argument("--attempts", type=positive_int, default=2)
    translate.add_argument("--force", action="store_true")
    translate.add_argument("--dry-run", action="store_true")

    merge = sub.add_parser("merge", help="Validate and merge chunk translations.")
    merge.add_argument("run_dir", type=Path)

    render = sub.add_parser("render", help="Render a translated PDF from merged translations.")
    render.add_argument("run_dir", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument(
        "--mode",
        choices=["translated", "bilingual", "overlay", "paper"],
        default="bilingual",
    )
    render.add_argument("--font-size", type=float, default=9.0)

    all_cmd = sub.add_parser("all", help="Prepare, translate, merge, and render in one command.")
    all_cmd.add_argument("pdf", type=Path)
    all_cmd.add_argument("--workdir", type=Path)
    all_cmd.add_argument("--output", type=Path)
    all_cmd.add_argument("--source-lang", default="English")
    all_cmd.add_argument("--target-lang", default="Japanese")
    all_cmd.add_argument("--chunk-chars", type=positive_int, default=6000)
    all_cmd.add_argument("--codex-bin", default="codex")
    all_cmd.add_argument("--model")
    all_cmd.add_argument("--attempts", type=positive_int, default=2)
    all_cmd.add_argument(
        "--mode",
        choices=["translated", "bilingual", "overlay", "paper"],
        default="bilingual",
    )
    all_cmd.add_argument("--font-size", type=float, default=9.0)
    all_cmd.add_argument("--force", action="store_true")

    status = sub.add_parser("status", help="Show chunk translation progress.")
    status.add_argument("run_dir", type=Path)

    markdown = sub.add_parser(
        "export-md",
        help="Export a Japanese Markdown paper with cropped figure/table assets.",
    )
    markdown.add_argument("run_dir", type=Path)
    markdown.add_argument("--output-dir", type=Path)
    markdown.add_argument("--filename", default="paper-ja.md")
    return parser


def show_status(run_dir: Path) -> None:
    run_dir = run_dir.expanduser().resolve()
    manifest = read_json(run_dir / "manifest.json")
    chunks = sorted((run_dir / "chunks").glob("chunk_*.json"))
    valid_count = 0
    invalid: list[str] = []
    for chunk_path in chunks:
        translated_path = run_dir / "translations" / chunk_path.name
        if not translated_path.exists():
            continue
        try:
            validate_translation(read_json(chunk_path), read_json(translated_path))
            valid_count += 1
        except Exception:
            invalid.append(chunk_path.name)
    print(f"PDF: {manifest['source_pdf_name']}")
    print(f"Pages: {manifest['page_count']}")
    print(f"Segments: {len(manifest['segments'])}")
    print(f"Chunks: {valid_count}/{len(chunks)} translated")
    if invalid:
        print(f"Invalid: {', '.join(invalid)}")
    if (run_dir / "translations.json").exists():
        print("Merged: yes")
    else:
        print("Merged: no")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "prepare":
        run_dir = prepare_run(
            pdf_path=args.pdf,
            workdir=args.workdir,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            chunk_chars=args.chunk_chars,
            force=args.force,
        )
        print(run_dir)
        return 0

    if args.command == "translate":
        outputs = translate_run(
            run_dir=args.run_dir,
            codex_bin=args.codex_bin,
            model=args.model,
            start=args.start,
            limit=args.limit,
            force=args.force,
            dry_run=args.dry_run,
            attempts=args.attempts,
        )
        print(f"translated {len(outputs)} chunk(s)")
        return 0

    if args.command == "merge":
        output = merge_translations(args.run_dir)
        print(output)
        return 0

    if args.command == "render":
        output = render_pdf(args.run_dir, args.output, args.mode, args.font_size)
        print(output)
        return 0

    if args.command == "all":
        run_dir = prepare_run(
            pdf_path=args.pdf,
            workdir=args.workdir,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            chunk_chars=args.chunk_chars,
            force=args.force,
        )
        translate_run(
            run_dir,
            codex_bin=args.codex_bin,
            model=args.model,
            force=args.force,
            attempts=args.attempts,
        )
        merge_translations(run_dir)
        output = render_pdf(run_dir, args.output, args.mode, args.font_size)
        print(output)
        return 0

    if args.command == "status":
        show_status(args.run_dir)
        return 0

    if args.command == "export-md":
        output_dir = args.output_dir or args.run_dir / "output" / "markdown"
        output = export_markdown(args.run_dir, output_dir, args.filename)
        print(output)
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
