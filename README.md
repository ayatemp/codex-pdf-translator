# Codex PDF Translator

PDF論文を、Codex CLIを使って日本語の読み物へ変換するローカル翻訳パイプラインです。

BabelDOCのように「PDFから構造を取り出し、翻訳し、読みやすい形に戻す」流れを参考にしています。ただし、このプロジェクトでは翻訳APIキーをツール側に持たせません。翻訳はローカルの `codex` CLIに任せるため、普段のCodexログイン状態をそのまま使えます。

現在のおすすめ出力は、次の2つです。

- `paper-ja.md`: 日本語本文に、図・表・疑似コードのスクリーンショットを埋め込んだMarkdown
- `paper-ja.pdf`: そのMarkdownをChrome/Chromiumで印刷して作る読みやすいPDF

元PDFのレイアウトを完全再現するよりも、「論文として読める日本語版」を作ることを優先しています。

## What It Does

- PDFからテキストブロック、ページ位置、図表領域を抽出します。
- 長い論文をCodexが扱いやすいJSON chunkへ分割します。
- `codex exec` をchunkごとに呼び出し、翻訳結果をJSONとして保存します。
- 翻訳済みchunkを `translations.json` に統合します。
- 図、表、疑似コードをPNGとして切り出し、Markdownに埋め込みます。
- 参考文献やシステム名など、英語のまま残すべき箇所をできるだけ保ちます。
- MarkdownをChrome/Chromiumの印刷エンジンでPDF化します。

従来のPDFレンダリングモードも残っています。

- `bilingual`: 左に元ページ画像、右に翻訳文
- `translated`: 翻訳文だけを流し込んだPDF
- `overlay`: 元PDF上に翻訳文を重ねる簡易overlay
- `paper`: 翻訳文を論文風に再組版するPDF

ただし、表や疑似コードを含む論文では、`export-md` と `render-md-pdf` を使うMarkdown経由の出力が一番読みやすいです。

## Requirements

- Python 3.10+
- `uv` 推奨
- Codex CLI
- MarkdownをPDF化する場合は、Google Chrome / Chromium / Brave / Edge のいずれか

Codex CLIがログイン済みか確認します。

```bash
codex login status
```

未ログインの場合は、通常のCodexログインを先に済ませてください。

## Install

このリポジトリのディレクトリで実行します。

```bash
uv venv
uv pip install -e ".[dev]"
```

`pip` だけで入れる場合:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

動作確認:

```bash
codex-pdf-translate --help
```

## Recommended Workflow

例として、`research/federated_learning/papers/navigating-data-heterogeneity.pdf` を翻訳する場合です。実際のファイル名に合わせて置き換えてください。

### 1. PDFを解析してrunを作る

```bash
codex-pdf-translate prepare \
  "../research/federated_learning/papers/navigating-data-heterogeneity.pdf" \
  --workdir runs/navigating-data-heterogeneity \
  --source-lang English \
  --target-lang Japanese
```

作成される主なファイル:

- `runs/<name>/source.pdf`: 入力PDFのコピー
- `runs/<name>/manifest.json`: 抽出されたページ、テキスト、座標情報
- `runs/<name>/chunks/chunk_0001.json`: Codexに渡す翻訳単位
- `runs/<name>/translations/`: chunkごとの翻訳結果の保存先

同じ `--workdir` で作り直したい場合は `--force` を付けます。

```bash
codex-pdf-translate prepare path/to/paper.pdf --workdir runs/my-paper --force
```

### 2. Codexで翻訳する

```bash
codex-pdf-translate translate runs/navigating-data-heterogeneity --model gpt-5.4-mini
```

途中まで翻訳したい場合:

```bash
codex-pdf-translate translate runs/navigating-data-heterogeneity --start 1 --limit 3
```

やり直したい場合:

```bash
codex-pdf-translate translate runs/navigating-data-heterogeneity --force
```

実際にCodexを呼ばず、呼び出し内容だけ確認したい場合:

```bash
codex-pdf-translate translate runs/navigating-data-heterogeneity --dry-run
```

進捗確認:

```bash
codex-pdf-translate status runs/navigating-data-heterogeneity
```

### 3. 翻訳結果を統合する

```bash
codex-pdf-translate merge runs/navigating-data-heterogeneity
```

これで `runs/navigating-data-heterogeneity/translations.json` が作られます。

### 4. Markdownを作る

```bash
codex-pdf-translate export-md \
  runs/navigating-data-heterogeneity \
  --output-dir runs/navigating-data-heterogeneity/output/markdown \
  --filename navigating-data-heterogeneity-ja.md
```

出力:

- `runs/<name>/output/markdown/navigating-data-heterogeneity-ja.md`
- `runs/<name>/output/markdown/assets/*.png`

`assets/` には、図、表、疑似コードなどのスクリーンショットが保存されます。Markdown内では通常の画像として参照されます。

### 5. MarkdownをPDFにする

```bash
codex-pdf-translate render-md-pdf \
  runs/navigating-data-heterogeneity/output/markdown/navigating-data-heterogeneity-ja.md \
  --output runs/navigating-data-heterogeneity/output/markdown/navigating-data-heterogeneity-ja.pdf
```

HTMLも同時に生成されます。

- `runs/<name>/output/markdown/navigating-data-heterogeneity-ja.html`
- `runs/<name>/output/markdown/navigating-data-heterogeneity-ja.pdf`

Chromeの場所を明示したい場合:

```bash
codex-pdf-translate render-md-pdf paper-ja.md \
  --output paper-ja.pdf \
  --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

## Short Version

慣れてきたら、この流れだけ覚えれば大丈夫です。

```bash
codex-pdf-translate prepare path/to/paper.pdf --workdir runs/my-paper
codex-pdf-translate translate runs/my-paper --model gpt-5.4-mini
codex-pdf-translate merge runs/my-paper
codex-pdf-translate export-md runs/my-paper --output-dir runs/my-paper/output/markdown
codex-pdf-translate render-md-pdf \
  runs/my-paper/output/markdown/paper-ja.md \
  --output runs/my-paper/output/markdown/paper-ja.pdf
```

## One-Shot PDF Rendering

`all` コマンドを使うと、PDFレンダリングまで一気に実行できます。

```bash
codex-pdf-translate all \
  path/to/paper.pdf \
  --workdir runs/my-paper \
  --mode bilingual \
  --model gpt-5.4-mini
```

これは `prepare -> translate -> merge -> render` をまとめたものです。Markdown出力までは行わないため、現在のおすすめであるMarkdown版・Markdown PDF版を作る場合は、`export-md` と `render-md-pdf` を別途実行してください。

## Other PDF Modes

Markdown経由ではなく、直接PDFを作る場合:

```bash
codex-pdf-translate render runs/my-paper --mode bilingual
codex-pdf-translate render runs/my-paper --mode translated
codex-pdf-translate render runs/my-paper --mode paper
codex-pdf-translate render runs/my-paper --mode overlay
```

使い分け:

- `bilingual`: 元PDFを見ながら翻訳を読みたいとき
- `translated`: とにかく翻訳文だけをPDFにしたいとき
- `paper`: 文章中心の論文を読みやすく再組版したいとき
- `overlay`: BabelDOC風に元PDF上へ翻訳を重ねたいとき

表、複雑な数式、疑似コードが多い論文では、直接PDFモードよりMarkdown経由のほうが安定します。

## Manual or Semi-Automatic Translation

Codexで自動翻訳せず、自分で翻訳JSONを編集することもできます。

`runs/<name>/translations/chunk_0001.json` のように、chunk名と同じファイルを作ります。

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

その後:

```bash
codex-pdf-translate merge runs/my-paper
codex-pdf-translate export-md runs/my-paper --output-dir runs/my-paper/output/markdown
```

各chunkの `id` は元の `chunks/chunk_XXXX.json` と完全一致している必要があります。

## Output Directory

典型的なrunディレクトリは次のようになります。

```text
runs/my-paper/
  source.pdf
  manifest.json
  chunks/
    chunk_0001.json
    chunk_0002.json
  translations/
    chunk_0001.json
    chunk_0002.json
  translations.json
  output/
    markdown/
      paper-ja.md
      paper-ja.html
      paper-ja.pdf
      assets/
        page-02-figure-01.png
        page-07-algorithm-01.png
```

`runs/` は生成物置き場です。公開リポジトリへ論文PDFや翻訳済み本文を入れたくない場合、このディレクトリはgit管理外のままにしてください。

## Tips

- 論文の読みやすい日本語版が欲しい場合は、まず `export-md` を使ってMarkdownを確認してください。
- 表やグラフは、テキスト化するよりスクリーンショットとして残すほうが読みやすい場合があります。
- 疑似コードは自動で `algorithm` 画像として切り出されます。
- 参考文献は原文のまま残す方針です。
- `translate` はchunk単位で再実行できます。長い論文で失敗しても、成功済みchunkを再利用できます。
- Codex CLIの利用は、通常のCodex利用枠や契約の影響を受ける可能性があります。このツールは別途OpenAI APIキーを埋め込まないだけです。

## Troubleshooting

### `Chrome/Chromium was not found`

Markdown PDF化にはChrome系ブラウザが必要です。Google Chrome、Chromium、Brave、Edgeのいずれかを入れるか、`--chrome` で実行ファイルを指定してください。

### `missing translation`

まだ翻訳されていないchunkがあります。

```bash
codex-pdf-translate status runs/my-paper
codex-pdf-translate translate runs/my-paper
codex-pdf-translate merge runs/my-paper
```

### Markdownの画像がPDFに入らない

`render-md-pdf` はMarkdownファイルの場所を基準にローカル画像を読みます。Markdownと `assets/` の相対関係を崩さないでください。

### overlay PDFの文字が小さい、または崩れる

`overlay` は元PDFのテキスト枠に日本語を押し込むため、長い文章では崩れやすいです。その場合はMarkdown出力を使ってください。

## Development

```bash
uv run pytest
```
