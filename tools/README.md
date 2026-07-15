# tools/ — content pipeline (Python)

These scripts turn the source **Grimoire PDFs** into the data the web app consumes.
They are **not** needed to run or host the site — only to regenerate content when a
new Grimoire version is published. The app itself is pure static HTML/CSS/JS.

## Requirements
Python 3.9+ with: `pip install -r tools/requirements.txt`

## Run
```bash
npm run ingest        # = bash tools/ingest.sh
```
Reads `tools/source/*.pdf` → writes `data/grimoire_*.json` and `assets/{icons,img}/`.

## Scripts
| file | job |
|---|---|
| `parse_grimoire.py`  | PDF text → structured nodes (font/column-aware, faithful text) |
| `extract_icons.py`   | game-icon glyphs → recolourable PNG masks + `icons.json` |
| `render_images.py`   | card-anatomy / icon-gallery pages → JPEG figures |
| `assemble.py`        | nodes → sections, cross-references, figures → `grimoire_*.json` |
| `validate_coverage.py` | checks parsed text is present in the source PDF |
| `ingest.sh`          | runs the whole pipeline |
