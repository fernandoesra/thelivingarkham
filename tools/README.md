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
| `card_anatomy.py`    | reads the card-anatomy chapter back out of the page's vector art |
| `render_images.py`   | icon-gallery pages, montages and anatomy cards → JPEG figures |
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

## What the book's typography means (`parse_grimoire.heading_role`)

The book says things with print that it never says in words, and the parser reads
them so no pack has to configure them:

| in the book | means | on the site |
|---|---|---|
| a big **callout-red** heading | a STOP! callout | a red-ruled box |
| a big **teal** heading | a subsection opens here | a teal heading with a rule |
| a big **plain** heading | nothing — just set larger | an ordinary entry |

That last row matters: the Spanish edition sets *La regla nefasta* two points
larger than its siblings and means nothing by it. Reading size alone made it a
*lesser* heading than the rules around it; reading colour too gets it right.

The teal is matched by range, not by one value — the Spanish and English editions
print it a shade apart (`#306360` vs `#30635F`).

### The book prints two reds, and means opposite things by them

| red | what it means | where it appears |
|---|---|---|
| `#8B1F24` · `#8B1F23` | **a STOP! callout** — read this twice | ES v1.0, EN v1.0 **and** EN v1.1 |
| `#911D1D` | **added in this edition** | 244× in EN v1.1; **not once** in either v1.0 |

That second row is the proof: a first edition adds nothing, and sure enough
neither first edition prints that red at all — while both print the callout red.
So the callout's red is emphasis, not a diff. Reading it as a diff made the
English **STOP!** box announce *"Rewritten in 1.1"* and appear in What's New,
when it is word-for-word what v1.0 printed.

The two sit about **six values apart on one channel**, so no threshold should be
trusted to split them — and none has to. The STOP! heading is *by definition*
printed in the callout red, so `learn_callout_red` simply asks each edition which
red is its callout red, and everything else red is an addition. No constant, no
language, no edition baked in. A pack whose edition has no callout at all gets
`None`, and then every red reads as an addition — which is right, because there is
no callout red for it to be confused with.

## Phase diagrams (`assemble.flow_of`)

Each phase is drawn in the book as a flowchart: teal boxes for the numbered
steps, red for the player windows, arrows between. The parser only sees the text
inside the boxes, so `flow_of` recognises the diagram by its **shape** and the app
rebuilds it. No wording is involved, so it works in any language:

* **step** — a bold lead ending in a number and a colon (`Paso 1.1:` / `Step 1.1:`)
  followed by the rest of the sentence
* **player window** — a block that opens with the game's free-trigger icon
* **go to** — a single bold + italic line

The prose that details the same phase cannot be mistaken for it: its headings are
a whole bold sentence with no colon.

`flow` is a *classification* of the entry's blocks (`[{kind, n, i}]`), not a copy
of them, so the text stays in one place and search still sees it.

### The loops (`assemble.flow_loops`)

The book curves arrows back up the right-hand side. Where each one goes is
written inside the boxes, so `flow_loops` reads it without knowing the language:

* a step sitting right below a player window that **names that window** loops back
  to it — the label is taken from the window box itself, not from a word list;
* a step that names an **earlier** step's number loops back to that step. Direction
  does the work: a number further down the diagram is just the next arrow.

Both were checked against the editions' own vector art (the loops are stroked
paths beside the boxes; `page.get_drawings()` finds them). The two rules reproduce
the three loops the book draws — 2.2.1→window and 2.2.2→2.2 in the investigation
phase, 3.3→window in the enemy phase — in both languages, with nothing spurious.
That is why the rules are trusted and the geometry is not shipped.

`loops` is `[[from, to], …]` of flow indices. The app measures how far each one
must reach (the text decides that, and it changes with the pane) and nests the
longest outermost, as the book does.

## Card anatomy (`card_anatomy.py`)

The book draws this chapter rather than writing it: a card, numbered diamonds
around it, a teal arrow curving from each diamond to the exact spot it means, and
a key explaining the numbers. Shipped as a page scan — which it used to be — none
of that text can be selected, searched, translated or read aloud, and the arrows
say nothing at all to anyone who cannot see them.

So it is read back out, and **only the card stays a picture**. Everything is found
by shape; no pack names a coordinate:

| in the book | found as |
|---|---|
| a card | a rounded rect — four corner curves and four sides (`clclclcl`) |
| an arrow | a fat teal Bézier + a teal triangle; the apex is the vertex opposite the shortest side |
| a numbered diamond | a big Teutonic number (set twice, so the text doubles: `13` → `1313`) |
| the key | a pale panel of `N. Term: description` items |

The arrow is the one thing the scan threw away, and it carries the meaning. Its
apex, as a percentage of the card, becomes a marker the reader can hover or focus;
the key becomes an ordered list, auto-linked into the glossary like any prose.

A card belongs to the last key seen at or before its page — which is how the book
reads, a key heading the cards it explains. The term is split from the description
on the **colon**, not on the bolding: the book bolds the term, but a single run can
straddle the colon, and the colon never lies.

> **Why this is trusted.** The Spanish edition spreads the chapter over four
> portrait pages; the English one compresses it onto two-page spreads. The layouts
> have nothing in common. Both are read by these rules alone and both come back
> with **13 cards, 50 markers and 2 keys** — and the same numbers on the same
> cards, with no arrow left pointing at nothing. Agreement that exact, across
> layouts that different, is not something a wrong rule produces.

### Getting the arrows off the cards (`strip_callouts`)

The book tucks the arrows and diamonds *over* the cards' edges, so a card clipped
straight off the page comes out with arrowheads and parchment wedges lying on it.
They are rebuilt as markers, so on the card itself they are damage — and they are
removed before the card is rendered, leaving everything else exactly as printed.

Each arrow is one self-contained block of the page's content stream whose `cm`
translate *is* the arrow's own end point — the very thing already located. So the
blocks are matched by geometry, not by their text. The diamonds are Form XObjects;
only the call that draws them on this page is dropped, never the XObject itself,
which may be shared. Redaction is the obvious tool and does not work here: MuPDF
does not count these paths as covered, and it would paint over the card art that
is the thing being kept.

`strip_callouts` must run **after** `build` — it erases the art `build` reads.

### Opting a pack in

One word: the chapter's section says `"kind": "anatomy"` instead of `"figures"`.
The pack already lists that chapter's figures, and each figure names its page, so
that list is where the pages come from — nothing else to declare. If the rebuild
comes back empty the section quietly falls back to `figures` and the page scans are
rendered after all, so a pack can never end up with a blank chapter. (When it
succeeds, those scans are not rendered at all — they are ~1.6 MB a language.)

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
