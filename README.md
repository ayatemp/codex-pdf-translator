# Codex PDF Translator

Codex PDF Translator is a local PDF translation pipeline inspired by BabelDOC's
"extract PDF structure, translate, rebuild PDF" workflow.

The key difference is the translation engine: this project can call the local
`codex` CLI for each translation chunk, so you do not need to put an OpenAI API
key into the PDF tool itself. It relies on your existing Codex login.

## What It Does

- Extracts text blocks and page geometry from a PDF with PyMuPDF.
- Splits the extracted text into JSON chunks that are friendly for Codex.
- Calls `codex exec` per chunk and validates strict JSON translations.
- Merges translated chunks into one `translations.json`.
- Renders a final PDF with ReportLab.
- Exports a Japanese Markdown reading file with cropped figure/table assets.
- Renders that Markdown to a styled PDF through local Chrome/Chromium.
- Supports three output modes:
  - `bilingual`: original page image on the left, translated text on the right.
  - `translated`: translated text only, reflowed for reading.
  - `overlay`: rough translated text overlay on top of original page blocks.
  - `paper`: translated text re-typeset as a clean paper-style reading PDF.

This is not a drop-in BabelDOC clone. It prioritizes a controllable,
agent-friendly workflow over pixel-perfect reconstruction.

## Requirements

- Python 3.10+
- Codex CLI, if you want automatic translation:

```bash
codex login status
```

If Codex CLI is not logged in, run the normal Codex login flow first.

## Install

From this directory:

```bash
uv venv
uv pip install -e ".[dev]"
```

Or with plain pip:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Quick Start

Prepare a PDF:

```bash
codex-pdf-translate prepare \
  "../research/federated_learning/papers/Inconsistency-Based Federated Active Learning.pdf" \
  --workdir runs/ifal \
  --source-lang English \
  --target-lang Japanese
```

Translate with Codex CLI:

```bash
codex-pdf-translate translate runs/ifal --model gpt-5.4-mini
```

Merge and render:

```bash
codex-pdf-translate merge runs/ifal
codex-pdf-translate export-md runs/ifal --output-dir runs/ifal/output/markdown
codex-pdf-translate render-md-pdf \
  runs/ifal/output/markdown/paper-ja.md \
  --output runs/ifal/output/markdown/paper-ja.pdf
```

Or run the whole flow:

```bash
codex-pdf-translate all \
  "../research/federated_learning/papers/Inconsistency-Based Federated Active Learning.pdf" \
  --workdir runs/ifal \
  --mode bilingual \
  --model gpt-5.4-mini
```

## Manual or Semi-Automatic Translation

You can skip `translate` and fill files in `runs/<name>/translations/` yourself.
Each file must match the chunk filename and use this shape:

```json
{
  "translations": [
    {
      "id": "p0001-b000",
      "target": "翻訳文"
    }
  ]
}
```

Then run:

```bash
codex-pdf-translate merge runs/ifal
codex-pdf-translate render runs/ifal --mode translated
```

## Notes

- `bilingual` mode is the most reliable for papers because it preserves the
  original page visually while giving you readable translated text.
- `paper` mode is the most readable Japanese output because it reflows the
  translation into a clean paper-like layout.
- `overlay` mode is useful for a BabelDOC-like feel, but long Japanese text may
  be shrunk or clipped inside the original English text boxes.
- Codex CLI usage may still count against your Codex plan or subscription. The
  project simply avoids embedding a separate OpenAI API key.
- The run directory is intentionally transparent: chunks, prompts, translations,
  and final PDFs are all inspectable files.
- Markdown export writes one `paper-ja.md` plus PNG assets under `assets/`.
  Use this when PDF layout reconstruction is less important than readable
  Japanese text with figures and tables preserved as screenshots.
- Markdown PDF rendering uses Chrome's print engine, so local image links such
  as `assets/page-02-figure-01.png` are embedded in the generated PDF.

## Development

```bash
pytest
```
