from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from codex_pdf_translator.codex_engine import merge_translations
from codex_pdf_translator.extract import prepare_run
from codex_pdf_translator.jsonio import read_json, write_json
from codex_pdf_translator.markdown_export import export_markdown
from codex_pdf_translator.md_pdf import markdown_to_html_document
from codex_pdf_translator.render import render_pdf


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.drawString(72, 720, "Federated active learning selects useful samples.")
    pdf.drawString(72, 700, "Client inconsistency can improve acquisition.")
    pdf.save()


def test_prepare_merge_render(tmp_path: Path) -> None:
    source_pdf = tmp_path / "paper.pdf"
    make_pdf(source_pdf)

    run_dir = prepare_run(
        source_pdf,
        tmp_path / "run",
        source_lang="English",
        target_lang="Japanese",
        chunk_chars=2000,
    )

    manifest = read_json(run_dir / "manifest.json")
    assert manifest["page_count"] == 1
    assert len(manifest["segments"]) >= 1

    chunk = read_json(run_dir / "chunks" / "chunk_0001.json")
    translated = {
        "translations": [
            {"id": item["id"], "target": f"翻訳: {item['source']}"}
            for item in chunk["segments"]
        ]
    }
    write_json(run_dir / "translations" / "chunk_0001.json", translated)

    merged = merge_translations(run_dir)
    assert merged.exists()

    output_pdf = render_pdf(run_dir, tmp_path / "translated.pdf", mode="translated")
    assert output_pdf.exists()
    assert output_pdf.stat().st_size > 0

    bilingual_pdf = render_pdf(run_dir, tmp_path / "bilingual.pdf", mode="bilingual")
    assert bilingual_pdf.exists()
    assert bilingual_pdf.stat().st_size > 0

    overlay_pdf = render_pdf(run_dir, tmp_path / "overlay.pdf", mode="overlay")
    assert overlay_pdf.exists()
    assert overlay_pdf.stat().st_size > 0

    paper_pdf = render_pdf(run_dir, tmp_path / "paper.pdf", mode="paper")
    assert paper_pdf.exists()
    assert paper_pdf.stat().st_size > 0

    markdown = export_markdown(run_dir, tmp_path / "markdown")
    assert markdown.exists()
    assert "翻訳:" in markdown.read_text(encoding="utf-8")

    html = markdown_to_html_document("# 見出し\n\n本文\n\n$$\nL_u = L_u^{cls}\n$$\n\n![図](assets/example.png)")
    assert "<h1>" in html
    assert "math-block" in html
    assert "assets/example.png" in html
