from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown


DEFAULT_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def protect_math_blocks(markdown_text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        formula = html.escape(match.group(1).strip())
        return f'\n\n<div class="math-block">{formula}</div>\n\n'

    return re.sub(r"(?ms)^\$\$\s*\n?(.*?)\n?\$\$\s*$", replace_block, markdown_text)


def find_chrome(chrome_path: str | None = None) -> str:
    if chrome_path:
        path = Path(chrome_path).expanduser()
        if path.exists():
            return str(path)
        resolved = shutil.which(chrome_path)
        if resolved:
            return resolved
        raise FileNotFoundError(f"Chrome executable not found: {chrome_path}")

    for command in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
        resolved = shutil.which(command)
        if resolved:
            return resolved

    for path in DEFAULT_CHROME_PATHS:
        if Path(path).exists():
            return path

    raise FileNotFoundError("Chrome/Chromium was not found")


def markdown_to_html_document(markdown_text: str, title: str = "Translated Paper") -> str:
    markdown_text = protect_math_blocks(markdown_text)
    body = markdown.markdown(
        markdown_text,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 16mm 20mm;
    }}
    html {{
      color: #171717;
      background: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans",
        "Hiragino Kaku Gothic ProN", "Yu Gothic", "Noto Sans CJK JP",
        "Noto Sans JP", Meiryo, sans-serif;
      font-size: 12px;
      line-height: 1.75;
    }}
    body {{
      max-width: 820px;
      margin: 0 auto;
      counter-reset: figure;
    }}
    h1 {{
      margin: 0 0 12px;
      text-align: center;
      font-size: 22px;
      line-height: 1.35;
      font-weight: 700;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 24px 0 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid #d8d8d8;
      font-size: 17px;
      line-height: 1.45;
      break-after: avoid;
    }}
    h3 {{
      margin: 18px 0 6px;
      font-size: 14px;
      line-height: 1.45;
      break-after: avoid;
    }}
    p {{
      margin: 0 0 9px;
      text-align: justify;
      overflow-wrap: anywhere;
    }}
    blockquote {{
      margin: 12px 0;
      padding: 8px 11px;
      border-left: 3px solid #7c8ea3;
      background: #f6f8fa;
      color: #333;
      break-inside: avoid;
    }}
    blockquote p {{
      margin: 0;
      text-align: left;
    }}
    .math-block {{
      margin: 10px 0 12px;
      padding: 8px 10px;
      border-left: 3px solid #586b82;
      background: #f8fafc;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 11px;
      line-height: 1.65;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      break-inside: avoid;
    }}
    img {{
      display: block;
      max-width: 100%;
      max-height: 235mm;
      height: auto;
      margin: 12px auto 8px;
      border: 1px solid #ddd;
      background: white;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    ul, ol {{
      margin: 6px 0 10px 22px;
      padding: 0;
    }}
    li {{
      margin: 3px 0;
    }}
    code {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.92em;
      background: #f2f2f2;
      padding: 0 3px;
      border-radius: 3px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0;
      font-size: 10px;
      break-inside: avoid;
    }}
    th, td {{
      border: 1px solid #d0d0d0;
      padding: 4px 5px;
      vertical-align: top;
    }}
    th {{
      background: #f0f3f6;
    }}
    a {{
      color: #1f5f99;
      text-decoration: none;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def render_markdown_pdf(
    markdown_path: Path,
    output_pdf: Path | None = None,
    output_html: Path | None = None,
    chrome_path: str | None = None,
) -> Path:
    markdown_path = markdown_path.expanduser().resolve()
    if output_pdf is None:
        output_pdf = markdown_path.with_suffix(".pdf")
    output_pdf = output_pdf.expanduser().resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    if output_html is None:
        output_html = output_pdf.with_suffix(".html")
    output_html = output_html.expanduser().resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    html_doc = markdown_to_html_document(
        markdown_path.read_text(encoding="utf-8"),
        title=markdown_path.stem,
    )
    output_html.write_text(html_doc, encoding="utf-8")

    chrome = find_chrome(chrome_path)
    with tempfile.TemporaryDirectory(prefix="codex-pdf-chrome-") as profile_dir:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={output_pdf}",
            str(output_html.as_uri()),
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=90,
            )
        except subprocess.TimeoutExpired as exc:
            if output_pdf.exists() and output_pdf.stat().st_size > 0:
                return output_pdf
            log_path = output_pdf.with_suffix(".chrome.log")
            log_path.write_text(exc.stdout or "", encoding="utf-8")
            raise RuntimeError(f"Chrome PDF rendering timed out; see {log_path}") from exc
        if result.returncode != 0:
            fallback = cmd.copy()
            fallback[1] = "--headless"
            try:
                result = subprocess.run(
                    fallback,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                    timeout=90,
                )
            except subprocess.TimeoutExpired as exc:
                if output_pdf.exists() and output_pdf.stat().st_size > 0:
                    return output_pdf
                log_path = output_pdf.with_suffix(".chrome.log")
                log_path.write_text(exc.stdout or "", encoding="utf-8")
                raise RuntimeError(f"Chrome PDF rendering timed out; see {log_path}") from exc
        if result.returncode != 0:
            log_path = output_pdf.with_suffix(".chrome.log")
            log_path.write_text(result.stdout, encoding="utf-8")
            raise RuntimeError(f"Chrome PDF rendering failed; see {log_path}")

    return output_pdf
