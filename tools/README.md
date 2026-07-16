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
| `render_images.py`   | card-anatomy / icon-gallery pages + montages → JPEG figures |
| `montages.py`        | config of the example card-art montages embedded in glossary entries |
| `assemble.py`        | nodes → sections, cross-references, figures → `grimoire_*.json` |
| `validate_coverage.py` | checks parsed text is present in the source PDF |
| `ingest.sh`          | runs the whole pipeline |

## Montage figures (example card-art inside glossary entries)

Some glossary entries include example **montages** (card-art + printed card text: *Move*,
*Victory X*) or **diagrams** (the slot icons in *Slots/Espacios*). In the PDF these are
**not** flat images — layers of art + live text — so the text bleeds into the entry body.
`montages.py` (`MONTAGES`) lists each one (page, clip region, `srcpage` for the credit,
target entry, alt, and an `info` HTML panel). From that single config:

* `render_images.py` renders the region to a flat JPEG (`<lang>-montage-*.jpg`),
* `parse_grimoire.py` masks the overlaid text out of the parsed body,
* `assemble.py` attaches the figure to its glossary entry.

The app centres the figure, wraps it in a credit band (*Grimoire figure · p. N · vX*) and
shows an **“i”** button that reveals the textual alternative.

### Standalone symbols (drawn as vectors)

The basic **weakness symbol** is drawn as PDF vector paths, so neither the text parser nor
the icon font sees it. `montages.py` handles it in two parts: `SYMBOL_MASKS` renders the
region to a recolourable alpha-mask icon (`extract_icons.py` → `assets/icons/weakness.png`
+ `icons.json`), and `INLINE_SYMBOLS` re-inserts it as a centred icon after the body block
whose text ends with a given anchor (e.g. *“…el siguiente símbolo:”*). Add new ones by
editing only `montages.py` and re-running `npm run ingest`.

## Version history (what's new between versions)

Each new Grimoire PDF marks the text **added in that version in dark red**. The parser
detects that red (`is_new_red`) and tags it; `assemble.py` turns it into version data:
new/updated entries, a `versions` manifest with dates, and a `whatsnew` index. The app
shows a "New version" banner on the landing, a **What's New** view, per-entry badges and
inline highlighting of the new text.

### Adding a new version (e.g. Spanish v1.1 later)
1. Put the new PDF in `tools/source/` and point the language's parse step at it in
   `ingest.sh` (replace the old file or update the path).
2. In `assemble.py`, add the version to that language's `CFG[...]['versions']` list
   (oldest → newest), with its release date, e.g.
   `'versions': [{'v':'1.0','date':'2026-05-11'}, {'v':'1.1','date':'YYYY-MM-DD'}]`.
   (Get the date from the PDF metadata: it's the `creationDate`.)
3. `npm run ingest`, then `npm run dev` to check. The newest version's red text becomes
   the highlighted "what's new"; everything is driven by the data, no app code changes.

> Note: the red in a PDF marks additions vs. the **immediately previous** version. With
> only two versions this yields an exact history. For 3+ versions with per-jump history,
> keep each version's data and diff (a future enhancement) — the data model (`v` per run,
> `versions[]`, `whatsnew{}`) already supports it.
