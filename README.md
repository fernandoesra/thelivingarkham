# The Living Arkham 🐙📖

An interactive, multilingual edition of the **Arkham Grimoire** — the rules-clarification compendium for *Arkham Horror: The Card Game* — **and** of the pre-2026 **FAQ (chapter 1)**. Two rulesets a decade apart, shown as two shelves, searched together: a glossary and rules, notes, errata and frequently-asked questions, with cross-references, ArkhamDB links and game icons. **v1.1**.

Run it locally: `npm run dev` → http://localhost:8080 · Static site, ready for GitHub Pages.

Available in **español · English · Deutsch · Italiano**. Want your language? → [Adding a language](#adding-a-language). Also have the FAQ document? → [The FAQ chapter 1 corpus](#the-faq-chapter-1-corpus).

---

## Adding a language

Everything one language needs lives in **one folder**, `langs/<code>/`. Adding a language means adding a folder — you never edit any code.

**You need:** the Grimoire PDF in your language, [Python 3.9+](https://www.python.org/downloads/), and the packages in `tools/requirements.txt` (`pip install -r tools/requirements.txt`).

### 1. Create the pack

```bash
python tools/new_lang.py nl          # use your language's code — one that has no pack yet
```

This creates:

```
langs/nl/
  source/      ← your PDFs go here (git-ignored: they never get committed)
  lang.json    ← describes your PDF          (fill in every TODO)
  ui.json      ← the interface, in English   (translate the values)
```

> **No Grimoire in your language?** You can still add the language — the interface, the
> landing page, the tutorial and the release notes, with every chapter saying plainly that
> the books are not available in it yet and offering the language that has them. That is one
> command and one file to translate: see
> [Adding a language without a rulebook](#adding-a-language-without-a-rulebook) below.

### 2. Put the PDFs in, and name them

Copy your PDF(s) into `langs/de/source/`, then list them in `lang.json`, **oldest first**:

```json
"book": {
  "title": "Das Arkham-Grimoire",
  "versions": [
    {"v": "1.0", "date": "2026-01-31", "pdf": "grimoire_de_v1_0.pdf"},
    {"v": "1.1", "date": "2026-04-12", "pdf": "grimoire_de_v1_1.pdf"},
    {"v": "1.2", "date": "2026-06-22", "pdf": "grimoire_de_v1_2.pdf"}
  ]
}
```

The newest PDF is the one readers see. **Ship the older ones too**: they are what the version history is built from — see [How versions work](#how-versions-work). The release date is in the PDF's own metadata (`creationDate`).

### 3. Describe your chapters

Ask the tool what your PDF actually contains:

```bash
python tools/inspect_pdf.py de --sections
```

It prints your chapter headings **and a ready-to-paste `"sections"` block**. Paste it into `lang.json` and fix the two things it can only guess:

* **`kind`** — `"glossary"` for the glossary, `"anatomy"` for the card-anatomy chapter, `"figures"` for the remaining picture-only chapters (icon tables, quick reference), `"rules"` for the rest.
* **`key`** — how the language switcher finds the same chapter in another language. It must come from the fixed list printed by the tool. Readers never see it.

`id` is the URL of the chapter (`#de/<id>`). Pick it once: changing it later breaks people's links.

### 4. Fill in the rest of `lang.json`

| field | what it is |
|---|---|
| `parse.introStart` | the first words of your "how to use this book" heading — lowercase, no accents |
| `parse.indexStart` | the first word of your book's **alphabetical index** — the parser reads up to it and stops. Careful: this is the index at the *back*, not the table of contents at the front (Spanish calls the first "Contenido" and the second "Índice"; German calls them "Inhalt" and "Index"). Point it at the front one and the parse ends on page 2. An edition that prints **no index** — the Italian one — says so with `""`, and is read to the end |
| `parse.introTitle` | the title for the landing page, e.g. `"Erste Schritte"` |
| `patterns.trigger` | the words that introduce a cross-reference, e.g. `"(siehe|vergleiche)\\b"` |
| `patterns.pageWord` / `patterns.pageRef` | how your book writes "page 13" |
| `autolink` | which glossary terms link automatically ([details](tools/README.md#auto-linked-related-terms-interactivity)) |
| `figures` | picture-only pages to render, e.g. `{"name": "card-anatomy-1", "page": 17}` |
| `montages` | card-art regions inside glossary entries — [see below](#pictures-inside-entries) |

These are regular expressions, so in JSON **backslashes are doubled**: write `\\s`, not `\s`. Copying `langs/en/lang.json` and swapping the words is the fastest way.

### 5. Translate the interface

`ui.json` starts as the English interface. Translate the values — and **you don't have to finish**: anything you leave in English stays English. Nothing breaks, and you can translate the rest later.

```json
"locale":      "de-DE",
"months":      ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"],
"datePattern": "{d}. {mon} {y}",
"alphabet":    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
"icons":       {"willpower": "Willenskraft", "...": "..."},
"themes":      {"slate": "Schiefer", "...": "..."},
"strings":     {"onthispage": "Auf dieser Seite",
                "entries": {"one": "Eintrag", "other": "Einträge"}, "...": "..."}
```

* `alphabet` — the letters of the A–Z filter, in **your** dictionary order. List only letters your language files separately: Spanish lists `Ñ` because *ñ* is its own letter, and leaves `Ú` out because *Única* files under **U**.
* `themes` — the theme names as the reader sees them in the picker. Translate the names, not the ids.
* `fallback` — the language to borrow untranslated strings from (`"en"` by default).
* `locale` — your language's BCP-47 tag. It is what picks the plural forms below, so it must be a real tag (`pt-BR`, not `ptbr`).

### Counted nouns

A few strings are printed after a number, and languages disagree about what that does. Write them as an object and the browser picks the form, using the plural categories your `locale` actually has — two for German, three for Polish, six for Arabic, one for Japanese:

```json
"entries": {"one": "Eintrag", "other": "Einträge"}
```

Write only the categories your language has. A plain string is still valid and is used for every count — which is the right answer for a language with one form, said on purpose rather than by accident.

### Language names

Nothing to do here, normally. Your pack's `name` in `lang.json` is your language's name **in your language** (`Deutsch`), and that is what the switcher shows — you find your language by looking for the word you know. When another language's name appears inside a sentence instead ("v1.1 came out in German"), the browser's own tables supply the reader's word for it, so a new pack is named correctly everywhere without anyone maintaining a list.

If your language's tables get one wrong, override just that one:

```json
"langNames": {"en": "Englisch"}
```

### 6. Add a flag (optional)

Drop a `flag.svg` into `langs/de/` — named exactly that, all lowercase — and re-run the build in step 7; the switcher picks it up. Keep it plain: it renders as a 20×14 chip, cropped to fit. No flag is fine — the button then shows just your label.

A flag names a country, and a language is not a country. So the flag is decoration only: the `label` and `name` in your pack are what identify the language, and they are what a screen reader announces.

### 7. Build it and look at it

```bash
python tools/ingest.py de     # just your language
npm run dev                   # → http://localhost:8080/#de/
```

Your language now appears in the switcher by itself. That's it — no code was touched.

If something is wrong, the build says so in a sentence, with the command to fix it. To check the pack without building:

```bash
python tools/langpack.py de
```

### Pictures inside entries

Some glossary entries show example card art (`montages`). In the PDF those are live text over artwork, so they are rendered to a flat image and their text is masked out of the entry body. To measure one, render the page with a coordinate grid:

```bash
python tools/inspect_pdf.py de --grid 9     # → assets/img/_inspect-p9.png
```

Read the corners off the red grid and write them down (`y` counts from the **top**):

```json
{"name": "montage-move", "page": 9, "srcpage": 17, "clip": [658, 156, 898, 281],
 "entry": "Bewegen", "alt": "…what the picture shows, for screen readers…",
 "info": "<p>…the card text, as an alternative to the image…</p>"}
```

`page` is the PDF page; `srcpage` is the page number printed in the book (they differ if your PDF is a two-page spread). Montages are optional — leave `"montages": []` if you don't want any.

### Sending it in

Open a pull request with `langs/<code>/` plus the files the build regenerated (`data/`, `assets/img/`). **Do not add the PDFs** — they are git-ignored on purpose (see the README inside `langs/<code>/source/`); the built `data/*.json` is what the site serves.

---

## Adding a language without a rulebook

The Grimoire and the FAQ exist in four languages. ArkhamDB serves eleven. A reader in one of the
other seven still gets the whole interface in their own words, and is told — in their own words —
that the books are not available yet, with a link to the language that has them.

```bash
python tools/new_lang.py fr --ui-only "Français" FR
```

That writes a two-field `lang.json` (`"uiOnly": true`) and a copy of the English `ui.json` to
translate. There is no `source/` folder, because there is nothing to put in it.

Then translate `langs/fr/ui.json` — all of it except the parts below — and drop a `flag.svg`
beside it if you have one. Nothing else: the shelf, the navigation and the routes are borrowed
from the language you fall back to, so every chapter already exists and already links across.

**Three rules that are not obvious**

1. **Fill in `mtnotice`.** It is empty in English and the site shows the notice *only* when the
   string is non-empty. If a machine translated your pack, say so there — the German pack is the
   model. A reader deserves to know which words nobody checked.
2. **Leave the game's own vocabulary in English.** Everything printed on a card or a product
   stays as it is: the 25 `icons`, `ubultimatums` / `ubboons` / `ubrefractions` and their type
   lines, the taboo categories, `tabooxp`. Inventing a translation for *Elder Sign* or *Boon*
   before the official manual exists means the site and the cards on the table disagree. The
   interface *around* them — buttons, labels, prose — is yours to translate.
3. **Counted nouns:** if your language has more plural forms than `one`/`other`, add the CLDR
   categories it needs (`few`, `many`) beside them. The site looks the category up by name, so
   the extra keys just work — Polish, Russian and Ukrainian all carry `few`.

When the rulebook does arrive in your language, the pack graduates: drop `"uiOnly"`, fill in the
book fields as above, and it becomes an ordinary language pack with everything already
translated.

---

## How versions work

The Grimoire is a living document: each edition adds entries and rewrites others. The site is always built from the **newest** edition you ship, and it tells the reader what changed and when.

Two different questions, two different answers:

| | question | where the answer comes from |
|---|---|---|
| **New** | Did this entry exist before? | comparing the editions — an entry is new in the first PDF that contains it |
| **Rewritten** | Which words changed? | the dark red the publisher prints for added text |

They are easy to confuse, and confusing them is wrong. In the English v1.1 fourteen entries have a red heading, but only **one** ("Search") is actually absent from v1.0 — the red heading means *"something in here changed"*, not *"this is new"*. "Replenish" is 96% red and still not new: it was rewritten, not added.

So: **the only way to know an entry is new is to have the previous PDF.** That is why the pack lists a file per version.

* **Ship every edition's PDF** and you get an exact history: each entry shows *"Added in v1.0 · Rewritten in v1.1"*, and the What's New page lets the reader browse any edition.
* **Ship only the newest** and the build says so. It can still highlight the red text — "these words are new" — but it will not claim any entry is new, because it cannot know.
* Skipping an edition in the middle is reported too: its changes get credited to the next edition that has a PDF.

Nothing here is language-specific. A language with a single edition simply has no history of its own.

### While a translation is on its way

A new edition comes out in English and the translations arrive months later. In the meantime, the language that is behind does **not** go quiet: its What's New page says that v1.1 exists, in which language, when it was published, and offers a button straight to it — and still shows which edition your language actually is on.

You do not configure any of this. The registry (`data/languages.json`) records each language's newest edition, so a language can tell that another one is ahead; ship the translated PDF and the notice is replaced by the real changelog on the next build. No language is hard-coded as "the source": whoever is ahead is ahead, so if a translation ever leads, the English page says the same thing.

## The FAQ chapter 1 corpus

Alongside the Grimoire (the 2026 rules), the site also carries the **retired FAQ** — FFG's pre-2026 *Notes, Errata, and Frequently Asked Questions*. They are two rulesets a decade apart, for the same game, and they can **contradict** each other — so the FAQ is a **separate, parallel corpus**, shown as its own **"FAQ chapter 1"** shelf below the Grimoire, and search runs over both at once and shows the results **split**, one document under each heading.

It is built by the same pipeline (`tools/faq.py`, run automatically by `ingest.py` after the Grimoire), into `data/faq_<code>.json`, in the very same shape as a grimoire file. To add it for a language:

1. Put the FAQ PDF in **`langs/<code>/source_faq/`**.
2. Add a **`"faq"`** block to `lang.json`, beside `"book"` — its versions and the section layout (each section's `anchor` is the heading text that starts it in the PDF):

```json
"faq": {
  "versions": [{"v": "2.5", "date": "2026-02-01", "pdf": "faq_de.pdf"}],
  "sections": [
    {"key": "faq-errata", "id": "c1-errata", "num": "", "title": "Notes and Errata",
     "kind": "rules", "anchor": "Notes and Errata"},
    {"key": "faq-questions", "id": "c1-questions", "num": "", "title": "Frequently Asked Questions",
     "kind": "faq", "anchor": "Frequently Asked Questions"}
  ]
}
```

3. Rebuild (`python tools/ingest.py <code>`). The FAQ shelf appears once `data/faq_<code>.json` exists.

Notes:

* **One version is a base.** Like the Grimoire, ship a file per version for a full history; a single version entry is a clean baseline (v2.5 today) with an empty *What's New*, and the machinery is ready for the day a new FAQ edition lands.
* **Links only ever point into the Grimoire.** The FAQ is retired, so its cross-references and auto-links resolve against the *Grimoire's* glossary, never inside itself; card references (`Name ( 20)`) go to **ArkhamDB**. Nothing links *into* the FAQ.
* Section `kind` is `"rules"` for prose, `"faq"` for the question-and-answer chapter (split into one entry per question automatically, by the italic-question / roman-answer typography), and `"icons"` for the product-icon reference (add `"build": "iconref"`, no `anchor` — it is rebuilt from the last page's art, not anchored prose). A `"rules"` section may also carry `"split": "term"` (Definitions: each bold term becomes an entry) or `"split": "numbered"` (Rulings: each `(N.NN)` clarification becomes an entry).
* The **set / campaign / scenario icons** printed before each card number are vector art, not font glyphs — recovered from the page, deduplicated by shape and slotted back in front of the number (`tools/faq_seticons.py`, shared SVGs in `assets/faqsets/`). The same tool rebuilds the icon-reference tables (campaigns, standalone products, starter decks, promos) into `assets/products/`.
* The FAQ prints the **bless/curse** chaos-token icons the Grimoire never uses; their glyphs are traced from the FAQ font and filled in automatically (`extract_icons.fill_from_faq`).
* Its **first two pages** — the cover (what the document is, what is new in this version) and the narrative epigraph — are read straight off the page by typography, not by an anchor, and become the shelf's opening chapter. Declare it with `{"key": "faq-intro", "id": "c1-intro", "build": "intro"}` as the first section; the app puts the "this is chapter 1, and it may contradict the Grimoire" warning on it, and every link that used to point at the retired FAQ document now lands there.

## Card links

A card reference in the books is a name, the product's icon, and the card's **collection number** — the position it holds inside its product. That is not a card id: ArkhamDB numbers each product's cards in its own run, and position 1 is a different card in every product ever printed. So the links are resolved by asking ArkhamDB itself (`tools/adb.py`, cached under `tools/other/_adb/`):

1. **Name and number** (`tools/adb_resolve.py`). One card printed at that position under that name *is* the card. Each unambiguous hit also **teaches** which campaign the reference's icon stands for — the icon is opaque vector art, but the cards beside it are not.
2. **The icon** settles the rest: "Daniela Reyes ( 1)" is two different cards until the mark between the bracket and the number says which campaign it belongs to.

3. **A hand answer.** A residue no matching can settle — the book and ArkhamDB disagree on the card's *name* ("Pierde tu alma" / "Vende tu alma") or on its *number*, or the card type is one the API does not serve — is answered in **`tools/card_links.json`**, consulted only after every automatic attempt has failed, so a hand answer can never override what the data proves. Each entry must match at least once or the build says so. The reasoning behind every one of them is kept in `tools/other/arkhamdb-missing-cards.md`.

Anything still unresolved keeps a **search** link, which lists every printing — an honest fallback beats a confident wrong card. Because the icon's campaign is *learned* rather than declared, each set icon also gets a real accessible name ("Legado de Dunwich") instead of a generic one, and a build where two references disagree about an icon says so.

Two supporting pieces:

* `tools/adb_names.py` finds the references the typographic matcher cannot see. That matcher recognises a reference by its *shape* — Capitalised Words before a bracketed number — which is how English titles are set and is why it quietly failed everywhere else. Spanish prints "Mercado de los bajos fondos ( 77)"; asking ArkhamDB "is there a card of this name at this position?" needs no capitalisation rule and cannot invent a card. It took the Spanish FAQ from 135 linked references to 365.
* `tools/grim_vecicons.py` recovers the product marks the **Grimoire** draws inside its sentences — the five investigator decks named in the optional rules, and the mark inside every "Name ( 20)". The FAQ patches the parser to inject these while it reads; the Grimoire's parse is long-tuned and measured against the printed page, so nothing there is touched: the PDF is scanned separately, each mark keyed by the words on either side of it, and they are slotted into the finished blocks afterwards.

## The community timing reference

The skill-test chapter carries a second, **fanmade** view: the community's breakdown of every triggering point with the cards that fire at each. It is not official, so it lives behind the chapter's own "everything / official diagram / fanmade diagram" switch, under a red notice saying exactly that and giving an address to report errors to. The sources are pictures (a scanned Spanish PDF, an English PNG), so they were transcribed by hand into `tools/fanmade_skilltest.json` — one block per language, each from its own document — and `tools/fanmade.py` files it under the chapter. It renders as a real table, not a screenshot: readable, searchable, translatable.

## The interactive taboo list

The Resources shelf carries a live **taboo list**, built from ArkhamDB's public API (`tools/taboos.py` → `data/taboos_<code>.json`). Every card on the current taboo list is grouped the way the book groups them — *Chained/Unchained* (an experience cost), *Mutated* (a rules-text change) and *Forbidden* (barred) — each with its collection number, its product icon (matched to the FAQ's own icon tables), and a **direct link** to the card on ArkhamDB in the reader's language. The mutation text ArkhamDB stores is English only, so it is tagged `lang="en"` and the list cross-links to the FAQ's own taboo chapter for the full write-up. It refreshes as part of `ingest.py` (network, best-effort: an offline build keeps the committed data), so `data/taboos_<code>.json` is **regenerated from ArkhamDB on every build** — don't hand-edit it, a fix there is lost on the next ingest. The translated mutation wording lives in the FAQ's own taboo chapter below the list; the editable card data for the viewer is a **separate** file (next section). Run it on its own with `python tools/taboos.py`.

## The taboo card renderer

Below the list, the same shelf **draws** every taboo-list card twice — as it is **printed** and as the **taboo** changes it — side by side, with the FFG change line beneath, so a reader compares the exact rules text without owning the card. Each face can be zoomed, and downloaded as a print-ready image (single card as PNG; **Download all** as a high-quality-JPEG `.zip` — the whole render runs in the reader's own browser, so a busy site never renders on the server, it only serves static plates). It is a fan reconstruction, flagged as one wherever the wording was rebuilt.

Two things are worth knowing before you touch it:

* **The card art is language-independent.** The plates in `assets/taboo/` (`plates/` for the screen, `plates-hi/` for print, plus `back.webp`) are **textless** — every word you see is drawn over them by the browser from the data file. So a new language reuses the shared plates and ships **only its data**.
* **Everything the renderer draws lives in one file per language,** `data/taboo_cards_<code>.json` — one record per card, keyed by its ArkhamDB `code`. The site fetches it directly, so a text fix shows on reload with no rebuild.

### Correcting a card or a translation

`data/taboo_cards_<code>.json` is the only file to touch for the viewer, and it is safe to touch: `ingest.py` does **not** rebuild it — the reconstruction that produced it is a separate, git-ignored pipeline — so a hand fix here survives a rebuild. Open the file, find the record by `code` (or `name`), fix it **in place** — keep the file's LF line endings, don't let an editor reformat the whole thing — and reload; the site fetches the file directly, so the change shows with no build step.

**Everything a reader sees is one of these — this is what you translate or correct:**

| field | the text it draws |
|---|---|
| `name`, `subname`, `traits`, `text`, `flavour` | the **printed** face, as ArkhamDB prints it in this language. Card icons are written as `[reaction]`, `[intellect]`, `[eldersign]`… |
| `pdf.note`, `pdf.paras`, `pdf.traits` | the **taboo** face — the reconstructed text with the change applied (rewritten rules for a *mutated* card; the printed text plus the "(+1 experience)" line for a *chained/unchained* one) |
| `change` | the one-line change note drawn under the pair, in this language (HTML, same icon codes) |

**Leave these alone.** `taboo.text` is the change *in English*:

```json
"taboo": { "text": "This card's ability gains: \"Remove Eucatastrophe from the game.\"" }
```

It is ArkhamDB's original wording, kept only as the source the language's `change` was written from. The viewer **never shows it** while `change` is set (which it always is), so **do not translate it** — seeing English here is expected, not a bug. The same goes for the codes and numbers that are not language at all: `cat` (grouping and badge), `rebuilt`/`assisted` (they drive the "reconstructed / AI-assisted" disclaimer), and the geometry and identity fields (`code`, `set`, `setAspect`, `w`, `h`, `cost`, `xp`, `faction`, `skills`, `stats`, …).

Send a correction as a PR with just the changed `data/taboo_cards_<code>.json`.

### Adding a language

1. **Produce the data file** `data/taboo_cards_<code>.json`. The fastest honest start is to copy `data/taboo_cards_en.json` and, record by record, replace the printed fields (`name`, `subname`, `traits`, `text`, `flavour`, `pdf.paras`) with ArkhamDB's text in your language and `change` with your FAQ's line; `cat` and the `code`s stay as they are. (The full reconstruction pipeline — ArkhamDB fetch, PDF geometry, the mutated-face rebuild — lives under `tools/other/taboo_proto/`, which is git-ignored because it is a large research build; the committed JSON is the shippable result.)
2. **Translate the interface strings.** Copy the `tb*` keys (`tbimpresa`, `tbtaboo`, `tbcat_*`, `tbdisclaimer`, `tbnoteline`, `tbzoom`, `tbfilters`, …) from `langs/en/ui.json` into `langs/<code>/ui.json` and translate the values. Anything left in English simply stays English.
3. **Rebuild.** `python tools/ingest.py <code>` (or just `python tools/langpack.py`, which rewrites the registry) — the renderer **auto-detects** `data/taboo_cards_<code>.json` and turns the viewer on for that language. You never edit `data/languages.json` by hand; a language that has no file simply falls back to the English cards behind a beta banner.

## The welcome tour

A first visit runs a six-stop tour (`tourStart` in `js/app.js`): what the site is, the language switch (and that English runs ahead), the theme picker, the search, the two rulebooks in the sidebar — *they are different rulesets and can disagree* — and who made it. No library: it is one scrim, one rectangle and one card, drawn **over** the page so nothing on it is restyled or re-stacked, and it is a real modal dialog (focus moves in, Tab is trapped, Escape leaves, each stop is a heading). It runs once, remembered in `localStorage` under `tla-tour`; the footer offers to replay it. A target that is not on screen — the sidebar on a narrow window — simply gets no rectangle and the stop reads as a centred card. Every string is in `ui.json` (`tour1t`…`tour6d`).

The **Ultimatums, Boons & Refractions** viewer merges the FAQ's chapter-1 refractions (5argon's card art, `tools/ub_cap1.py`) with the Grimoire's own, filterable by chapter (Cap. 1 / Cap. 2), by type (a refraction is itself either an ultimatum or a boon) and, within the refractions, by campaign and scenario; in list view a stepper leafs through the shown cards, dimming its arrow at each end of the stack. Each refraction card carries its scenario's encounter-set symbol, its campaign symbol and its illustrator: the campaign mark is derived from the FAQ's own icon table, and the scenario marks are cut from the artist's vector symbol sheets by `tools/scenario_icons.py` (which records exactly which mark on which sheet is which scenario — never a bitmap trace).

## Corrections

The parser is faithful: it copies the book's words and does not guess. A content audit turns up two things that leaves behind, and `tools/text_fixes.json` answers both, once and visibly, instead of hiding them in the parser:

* **extraction** — the PDF says the right thing but its text layer breaks it (a word split across a line break, a hyphen lost at one);
* **source** — the official PDF carries the typo itself. We correct it rather than teach it, and the rule records that we are knowingly diverging from the printed text.

Every rule must match at least once or the build says so, so a rule left over from a reprint is never silently wrong. `python tools/text_fixes.py` lists them.

## How it fits together

```
langs/<code>/        the only thing a translator writes  (lang.json · ui.json · flag.svg · source/*.pdf · source_faq/*.pdf)
tools/               the pipeline — knows no language     (python tools/ingest.py)
data/                generated: grimoire_<code>.json + faq_<code>.json + taboos_<code>.json + languages.json (the registry) — plus hand-written data/releases.json (the release notes, every language in one file, fetched when the footer's release panel opens)
assets/              generated figures + the game icons (shared by every language)
index.html js/ css/  the app — knows no language
```

The app reads `data/languages.json` to learn which languages exist (and which have a FAQ corpus, via `faqData`), and fetches a language only when it is first shown. A language is listed there only once its content has actually been built, so a half-finished pack can sit in `langs/` without putting a dead button in the header. The FAQ is optional per language: a pack without a `"faq"` block simply has no FAQ shelf.

Pipeline details (parser, auto-links, icons, montages): [`tools/README.md`](tools/README.md).
Putting it on a server: [`deploy.md`](deploy.md).

## Commands

| command | what it does |
|---|---|
| `npm run dev` | serve the site locally |
| `npm run ingest` | rebuild every language |
| `npm run ingest -- de` | rebuild one language |
| `npm run lang:new -- de` | start a new language pack |
| `npm run lang:check` | validate every pack |
| `npm run lang:inspect -- de --sections` | list a PDF's chapters |

## License

Code: CC-BY-NC-4.0 · The rules text belongs to its authors. *Arkham Horror: The Card Game* ™ Fantasy Flight Games. A [Rincón Miskatonic](https://rinconmiskatonic.org/) project.
