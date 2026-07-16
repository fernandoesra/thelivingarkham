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

`extract_icons.py` pulls the Arkham font out of the PDF and traces each glyph to
`assets/icons/<name>.svg`, then writes **`css/icons.css`** (generated — don't edit it).

The size matters as much as the shape. A font knows exactly how big each glyph is and
where it sits on the baseline: *unique* is a small 0.39em mark, *free* is a wide 2.12em
arrow. Drawing both into the same square box — which is what the old raster masks did —
made unique 2.7x too big and free less than half its size. So each icon carries its own
width, height and baseline offset in em, and `--icon-scale` (in `app.css`) nudges them
all together without disturbing their proportions. Glyphs shorter than `MIN_HEIGHT_EM`
are grown to it, because a faithful 0.39em speck is not readable on a screen.

The basic-weakness symbol is drawn art rather than a glyph, so it is still clipped from
the page to a PNG mask and sized like a capital letter.

## Version history (`history.py`)

Each Grimoire PDF prints the text **added in that edition in dark red**. That red is
precise about *which words* are new — and says nothing reliable about *which entries*
are new. The two are constantly confused; they must not be.

Measured on the real English editions:

* 14 entries in v1.1 carry a **red heading**. Only **one** ("Search") is absent from v1.0.
  A red heading means "something in this entry changed".
* "Replenish" is **96% red** and existed in v1.0 — so "mostly red ⇒ new" fails too.
* "Act Deck and Agenda Deck" is **0.7% red**, and the old code called it a new entry.

So `history.build()` answers the two questions from two sources:

| field | meaning | derived from |
|---|---|---|
| `addedIn` | the edition the entry first appeared in | parsing every edition's PDF and comparing |
| `changedIn` | editions that rewrote part of it | the red runs inside that edition |
| run `v` | this run of text was added in that edition | the red itself |

Older editions are parsed **without montage masking** (their clips belong to a different
layout) and only their entry list and red flags are used, so the layout difference costs
nothing.

`addedIn` is `null` when it cannot be known — a pack whose older PDFs are missing gets
no "New" claims rather than false ones. Gaps are reported by `ingest.py`.

To add a version: put the new PDF in `langs/<code>/source/`, append it to that pack's
`book.versions` (oldest → newest) with its release date, and re-run
`python tools/ingest.py <code>`. Keep the older PDFs — they are the history.

> If an edition does not use red markup at all, `whatsnew` comes out empty and the
> section never appears. `ingest.py` warns when that happens, so it can't be mistaken
> for a bug.
