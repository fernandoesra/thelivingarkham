# tools/ — content pipeline (Python)

These scripts turn the source **Grimoire PDFs** into the data the web app consumes.
They are **not** needed to run or host the site — only to regenerate content when a
new Grimoire version is published, or when a language is added. The app itself is
pure static HTML/CSS/JS.

**No script here knows about any specific language.** Everything language-specific
lives in a language pack, `langs/<code>/lang.json`. To add a language, see
[Adding a language](../README.md#adding-a-language) — you will not need this file.

## Requirements
Python 3.9+ with: `pip install -r tools/requirements.txt`

## Run
```bash
python tools/ingest.py          # every language   (= npm run ingest)
python tools/ingest.py de       # just one
```
Reads `langs/*/source/*.pdf` → writes `data/grimoire_<code>.json`, `data/languages.json`
and `assets/{icons,img}/`.

## Scripts
| file | job |
|---|---|
| `langpack.py`        | finds, loads and validates the language packs; builds the registry |
| `icons.py`           | the icon font's codepoint → name map (shared, language-independent) |
| `parse_grimoire.py`  | PDF text → structured nodes (font/column-aware, faithful text) |
| `extract_icons.py`   | game-icon glyphs → recolourable PNG masks |
| `render_images.py`   | card-anatomy / icon-gallery pages + montages → JPEG figures |
| `assemble.py`        | nodes → sections, cross-references, auto-links, figures → `grimoire_<code>.json` |
| `validate_coverage.py` | checks parsed text is present in the source PDF |
| `ingest.py`          | runs the whole pipeline for one or every language |
| `new_lang.py`        | scaffolds a new pack |
| `inspect_pdf.py`     | shows a PDF's chapters, or a coordinate grid for measuring montages |

Each script takes a **language code** and asks `langpack.py` for the rest:
`python tools/assemble.py es`. A malformed pack fails with a message aimed at its
author, never a traceback — and never a run that "succeeds" with content missing.

## Where the intermediate files go

`data/_nodes_<code>.json` (parsed nodes) and `assets/img/images_<code>.json` (figure
sizes) are build artifacts and are git-ignored; `ingest.py` passes them in memory.
They are per-language so that rebuilding one language can never truncate another's.

## Auto-linked related terms (interactivity)

Besides the explicit *"Consulta también"* cross-references, `assemble.py` (`autolink`)
turns the **first mention** of a related glossary term into an inline link, so the reader
can jump straight to it (e.g. *"Robar 1 carta"* in **Acciones básicas** → the **Robar
cartas** entry). It renders as the same `xref` link the app already handles, so clicking
navigates and the browser **Back** button returns you where you came from.

It is deliberately conservative (glossary only, so it never floods the rules chapters):
* multi-word titles link by default; single-word titles only if listed in `autolink.allowSingleWord`
  (distinctive keywords — *Moverse*, *Cazador*, *Represalia*…), which keeps common words
  like *acción* / *carta* / *lugar* from over-linking;
* `autolink.alias` maps wordings that differ from the title (verb forms, the basic-action
  list: `'robar 1 carta' → 'Robar cartas'`);
* `autolink.stop` blocks function phrases (*"a continuación"*, *"por cada"*…);
* one link per target per entry, never self-links, capped by `autolink.cap`.

Matching is accent/case-insensitive and spans runs (so a bold lead word doesn't hide the
phrase). Tune the lists in your pack's `lang.json` and re-run `python tools/ingest.py <code>`.

> The accent fold used for matching is **length-preserving** (`langpack.validate_fold`):
> offsets in the folded text are mapped straight back onto the original runs, so a
> one-to-many mapping such as `ß → ss` would silently corrupt every link after it. That
> invariant is enforced in code, not just documented.

## Montage figures (example card-art inside glossary entries)

Some glossary entries include example **montages** (card-art + printed card text: *Move*,
*Victory X*) or **diagrams** (the slot icons in *Slots/Espacios*). In the PDF these are
**not** flat images — layers of art + live text — so the text bleeds into the entry body.
A pack's `montages` list declares each one (page, clip region, `srcpage` for the credit,
target entry, alt, and an `info` HTML panel). From that single config:

* `render_images.py` renders the region to a flat JPEG (`<code>-montage-*.jpg`),
* `parse_grimoire.py` masks the overlaid text out of the parsed body,
* `assemble.py` attaches the figure to its glossary entry.

The app centres the figure, wraps it in a credit band (*Grimoire figure · p. N · vX*) and
shows an **“i”** button that reveals the textual alternative.

Clip coordinates belong to **one specific PDF edition**, not to a language: if a pack
points at a differently-laid-out file, the parser refuses rather than masking the wrong
region. Measure them with `python tools/inspect_pdf.py <code> --grid <page>`.

### Standalone symbols (drawn as vectors)

The basic **weakness symbol** is drawn as PDF vector paths, so neither the text parser nor
the icon font sees it. A pack handles it in two parts: `iconArt.symbols` renders the
region to a recolourable alpha-mask icon (`extract_icons.py` → `assets/icons/weakness.png`),
and `inlineSymbols` re-inserts it as a centred icon after the body block whose text ends
with a given anchor (e.g. *“…el siguiente símbolo:”*).

### The game icons are shared

The icon glyphs are identical in every edition, so exactly **one** pack renders them —
the one with `"iconArt": {"provides": true}` (currently `es`). Every other pack just
supplies the labels, in `ui.json` under `icons`. If that pack's PDF isn't on your machine,
icon rendering is skipped and the committed artwork is reused — which is normal and fine.

## Version history (what's new between versions)

Each new Grimoire PDF marks the text **added in that version in dark red**. The parser
detects that red (`is_new_red`) and tags it; `assemble.py` turns it into version data:
new/updated entries, a `versions` manifest with dates, and a `whatsnew` index. The app
shows a "New version" banner on the landing, a **What's New** view, per-entry badges and
inline highlighting of the new text.

To add a version: put the new PDF in `langs/<code>/source/`, append it to that pack's
`book.versions` (oldest → newest) with its release date, and re-run
`python tools/ingest.py <code>`. Only the newest PDF is parsed; everything else is data.

> Note: the red in a PDF marks additions vs. the **immediately previous** version. With
> only two versions this yields an exact history. For 3+ versions with per-jump history,
> keep each version's data and diff (a future enhancement) — the data model (`v` per run,
> `versions[]`, `whatsnew{}`) already supports it.
>
> If an edition does not use red markup at all, `whatsnew` comes out empty and the section
> never appears. `ingest.py` warns when that happens, so it can't be mistaken for a bug.
