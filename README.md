# The Living Arkham 🐙📖

An interactive, multilingual edition of the **Arkham Grimoire** — the rules-clarification compendium for *Arkham Horror: The Card Game*. Searchable glossary, cross-references and game icons. **v0.1.0 · beta**.

Run it locally: `npm run dev` → http://localhost:8080 · Static site, ready for GitHub Pages.

Available in **español · English**. Want your language? → [Adding a language](#adding-a-language).

---

## Adding a language

Everything one language needs lives in **one folder**, `langs/<code>/`. Adding a language means adding a folder — you never edit any code.

**You need:** the Grimoire PDF in your language, [Python 3.9+](https://www.python.org/downloads/), and the packages in `tools/requirements.txt` (`pip install -r tools/requirements.txt`).

### 1. Create the pack

```bash
python tools/new_lang.py de          # use your language's code: de, fr, it, pt…
```

This creates:

```
langs/de/
  source/      ← your PDFs go here
  lang.json    ← describes your PDF          (fill in every TODO)
  ui.json      ← the interface, in English   (translate the values)
```

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
| `parse.indexStart` | the first word of your index/contents heading (the parser stops there) |
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
"months":      ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"],
"datePattern": "{d}. {mon} {y}",
"alphabet":    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
"icons":       {"willpower": "Willenskraft", "...": "..."},
"themes":      {"slate": "Schiefer", "...": "..."},
"strings":     {"onthispage": "Auf dieser Seite", "...": "..."}
```

* `alphabet` — the letters of the A–Z filter, in **your** dictionary order. List only letters your language files separately: Spanish lists `Ñ` because *ñ* is its own letter, and leaves `Ú` out because *Única* files under **U**.
* `themes` — the theme names as the reader sees them in the picker. Translate the names, not the ids.
* `fallback` — the language to borrow untranslated strings from (`"en"` by default).

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

Open a pull request with `langs/<code>/` plus the files the build regenerated (`data/`, `assets/img/`). If your PDF is too large for GitHub, say so in the PR and we'll sort it out.

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

## How it fits together

```
langs/<code>/        the only thing a translator writes  (lang.json · ui.json · flag.svg · source/*.pdf)
tools/               the pipeline — knows no language     (python tools/ingest.py)
data/                generated: grimoire_<code>.json + languages.json (the registry)
assets/              generated figures + the game icons (shared by every language)
index.html js/ css/  the app — knows no language
```

The app reads `data/languages.json` to learn which languages exist, and fetches a language only when it is first shown. A language is listed there only once its content has actually been built, so a half-finished pack can sit in `langs/` without putting a dead button in the header.

Pipeline details (parser, auto-links, icons, montages): [`tools/README.md`](tools/README.md).

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
