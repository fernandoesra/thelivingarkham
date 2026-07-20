# -*- coding: utf-8 -*-
"""Build the "FAQ chapter 1" corpus — a second, parallel document to the Grimoire.

The retired FAQ (FFG's "Notes, Errata, and Frequently Asked Questions", the pre-2026
rules) is a separate PDF that lives beside the Grimoire in each language pack, under
`langs/<code>/source_faq/`. It is a whole document in its own right — errata,
definitions, rulings, a Q&A, the taboo list, the legacy Ultimatums/Boons/Refractions,
the environments — so it is built into its own data file, `data/faq_<code>.json`, in the
SAME shape as the Grimoire, and shown as its own shelf in the navigation.

Why a separate corpus and not a Grimoire chapter: the Grimoire (2026) and this FAQ are
two rulesets a decade apart. They cover the same game and can *contradict* each other,
so the site keeps them apart and searches both at once, side by side. The one rule that
crosses the line is deliberate: a cross-reference inside the FAQ always points at the
*Grimoire* — the FAQ is retired, so the living reference it links to is the new book,
never itself. That is why the auto-linker here is fed the Grimoire's glossary, and card
references go to ArkhamDB (external), and nothing ever links *into* this corpus.

This reuses the Grimoire pipeline wholesale — `parse_grimoire.parse_pdf` for the PDF,
`assemble.split_qa`/`linkify`/`autolink` and `cardlinks` for the structure and links —
and adds only the thin, FAQ-specific part: mapping this document's headings onto a
declared section layout (which differs subtly between languages, so it is declared per
language in `lang.json` -> "faq", exactly as the Grimoire's sections are).

Usage:  python tools/faq.py [<lang> ...]     (writes data/faq_<code>.json)
"""
import copy
import json
import os
import re
import sys

import fitz

import langpack
import parse_grimoire
import assemble
import cardlinks
import text_fixes
import faq_seticons
import adb_names
import adb_resolve

DATA_DIR = langpack.DATA_DIR
GROUP = 'chapter1'                       # the navigation shelf, below the Grimoire


# ---- config ----------------------------------------------------------------
def faq_cfg(pack):
    """The pack's FAQ configuration, or None if this language has no FAQ yet.

    Lives under a "faq" key in langs/<code>/lang.json — invisible to the Grimoire
    pipeline (which only reads the fields it knows) so the two never interfere."""
    cfg = pack.raw.get('faq')
    if not cfg:
        return None
    if not cfg.get('versions'):
        raise langpack.PackError(
            f'langs/{pack.code}/lang.json: "faq" needs a "versions" list (oldest first), '
            f'e.g. [{{"v": "2.5", "date": "2026-02-01", "pdf": "faq_es.pdf"}}].')
    if not cfg.get('sections'):
        raise langpack.PackError(
            f'langs/{pack.code}/lang.json: "faq.sections" is empty — there would be '
            f'nothing to read out of the FAQ PDF.')
    return cfg


def faq_pdf(pack, cfg):
    newest = cfg['versions'][-1]
    path = os.path.join(pack.dir, 'source_faq', newest['pdf'])
    if not os.path.exists(path):
        raise langpack.PackError(
            f"langs/{pack.code}: the FAQ PDF for v{newest['v']} is missing.\n"
            f"  expected: langs/{pack.code}/source_faq/{newest['pdf']}\n"
            f"  Put the file there, or fix \"faq.versions[].pdf\" in "
            f"langs/{pack.code}/lang.json.")
    return path


# ---- nodes -> sections -----------------------------------------------------
def merge_wrapped_headings(nodes):
    """A heading that wrapped onto two lines is parsed as two nodes, the first with
    no body ("2. Interpretation of" + "card abilities", "Environments current, legacy"
    + "and limited (Beta)"). Fuse an empty heading node into the next heading of the
    same level, joining the titles and keeping the second's body."""
    out = []
    i = 0
    while i < len(nodes):
        n = nodes[i]
        nxt = nodes[i + 1] if i + 1 < len(nodes) else None
        if (not n['blocks'] and nxt is not None and nxt['level'] == n['level']
                and n['title'] and n['title'] not in ('(frontmatter)',)):
            merged = dict(nxt)
            merged['title'] = (n['title'].rstrip() + ' ' + nxt['title'].lstrip()).strip()
            if n.get('title_runs') or nxt.get('title_runs'):
                merged['title_runs'] = (n.get('title_runs', []) + nxt.get('title_runs', []))
            out.append(merged)
            i += 2
            continue
        out.append(n)
        i += 1
    return out


def title_runs_of(node):
    """A heading's rich title if it carries an icon, else a single plain run."""
    if node.get('title_runs'):
        return node['title_runs']
    return [{'kind': 'text', 't': node['title'], 'bold': False, 'italic': False,
             'ref': False}]


# ---- splitting prose into entries by its own typographic leads ---------------
# Two of the FAQ's chapters are written as a list whose "headings" are typographic, not
# structural — the parser sees one wall of prose. Rebuilt into real entries so each gets a
# §anchor and its own line in search, exactly as split_qa does for the questions.
_NUM_LEAD = re.compile(r'^\s*\(\d+(?:\.\d+)?\)')


def _is_fully_bold(block):
    """A block that is entirely bold: the Definitions chapter sets each term this way."""
    txt = [r for r in block['runs'] if r.get('kind') == 'text' and r.get('t', '').strip()]
    return bool(txt) and all(r.get('bold') for r in txt)


def _lead_bold_title(block):
    """'(1.1) Attacks of opportunity  The attacks…' -> (title_runs, body_runs): the leading
    bold (and icon) runs are the numbered heading, the rest is the first body paragraph."""
    runs = block['runs']
    i = 0
    while i < len(runs) and (runs[i].get('kind') == 'icon'
                             or (runs[i].get('kind') == 'text' and runs[i].get('bold'))):
        i += 1
    return [dict(r) for r in runs[:i]], [dict(r) for r in runs[i:]]


def _has_content(runs):
    return any((r.get('t', '').strip() or r.get('kind') == 'icon') for r in runs)


def split_terms(blocks):
    """Definitions: a wholly-bold block is a term heading; the blocks under it are its body.
    Anything before the first term stays as the chapter lead."""
    lead, entries, cur = [], [], None
    for b in blocks:
        if b.get('type') != 'bullet' and _is_fully_bold(b) and len(assemble.flat_text(b['runs'])) < 90:
            cur = {'title': assemble.flat_text(b['runs']).strip(' .:'),
                   'titleRuns': [dict(r) for r in b['runs']], 'blocks': []}
            entries.append(cur)
        elif cur is not None:
            cur['blocks'].append(b)
        else:
            lead.append(b)
    return lead, entries


def _split_at_numbered_leads(block):
    """Split a block wherever a bold '(N.NN)' heading begins part-way through it. When a
    clarification's heading flows straight out of the previous one — across a column or page
    break — it lands glued inside the previous block (often a bullet), so its "(1.19) …" is not
    that block's first run and the numbered split walks right past it. Cutting the block at each
    such lead makes every heading a block start again (this recovered 1.3, 1.15–1.17, 1.19)."""
    runs = block.get('runs', [])
    cuts = [i for i, r in enumerate(runs)
            if i > 0 and r.get('kind') == 'text' and r.get('bold')
            and _NUM_LEAD.match(r.get('t', ''))]
    if not cuts:
        return [block]
    bounds = [0] + cuts + [len(runs)]
    out = []
    for k in range(len(bounds) - 1):
        seg = runs[bounds[k]:bounds[k + 1]]
        if not seg:
            continue
        # A segment that STARTS with a numbered heading is a paragraph (a clarification is never
        # a bullet); the leading segment keeps the block's own type.
        nb = dict(block)
        nb['runs'] = seg
        nb['type'] = block.get('type', 'p') if k == 0 else 'p'
        out.append(nb)
    return out


def split_numbered(blocks):
    """Rulings: a paragraph opening with a bold '(N.NN)' is a clarification. Its bold lead is
    the heading; the rest of that paragraph and the blocks under it are the body."""
    expanded = []
    for b in blocks:
        expanded.extend(_split_at_numbered_leads(b))
    blocks = expanded
    lead, entries, cur = [], [], None
    for b in blocks:
        r0 = b['runs'][0] if b['runs'] else {}
        if (b.get('type') != 'bullet' and r0.get('kind') == 'text' and r0.get('bold')
                and _NUM_LEAD.match(r0.get('t', ''))):
            title, body = _lead_bold_title(b)
            cur = {'title': assemble.flat_text(title).strip(' .:'), 'titleRuns': title,
                   'blocks': ([{'type': 'p', 'runs': body}] if _has_content(body) else [])}
            entries.append(cur)
        elif cur is not None:
            cur['blocks'].append(b)
        else:
            lead.append(b)
    return lead, entries


# The icon-reference chapter's group headings — "Iconos de campaña", "Iconos promocionales",
# "Campaign Product Icons", "Promo Icons", … — all name icons, and nothing else in the FAQ does
# at heading level (the "(1.9) Iconos de habilidad comodín" ruling is an inline bold lead inside
# prose, never a heading node). Folded, both languages carry the word "icon"/"icono"/"icons".
_ICONREF_HEAD = re.compile(r'\bicono?s?\b')


def _is_iconref_heading(node):
    return bool(node.get('title') and _ICONREF_HEAD.search(assemble.norm(node['title'])))


def group_sections(nodes, cfg):
    """Walk the flat node stream and split it into the declared FAQ sections.

    A node whose title matches a section's "anchor" starts that section; its own body
    becomes that section's lead. Every following node (until the next anchor) is an
    entry of the current section. Anchors are matched language-neutrally on folded,
    normalised text, by prefix — so a wrapped/edition-quirked heading still matches."""
    anchors = []                                       # (folded_anchor, section_cfg)
    for sc in cfg['sections']:
        if sc.get('build'):                            # built specially, not anchored (icons)
            continue
        anchors.append((assemble.norm(sc.get('anchor', sc['title'])), sc))

    def match(title):
        nt = assemble.norm(title)
        for a, sc in anchors:
            if nt == a or nt.startswith(a):
                return sc
        return None

    secs = []
    cur = None
    for n in nodes:
        if n['title'] == '(frontmatter)':
            continue
        sc = match(n['title'])
        if sc is not None:
            cur = {'cfg': sc, 'intro': list(n['blocks']), 'members': []}
            secs.append(cur)
        elif _is_iconref_heading(n):
            # The icon-reference tables ("Iconos de campaña" / "Campaign Product Icons", …) are
            # rebuilt structurally by faq_seticons.extract_iconref, not read as prose. They sit
            # at the very end — a whole last page (ES) or the second column of it (EN) — with no
            # anchor of their own, so without this they fall into the last prose section
            # (Environments), dragging the campaign list and "Iconos de campaña" heading into it.
            cur = None
        elif cur is not None:
            cur['members'].append(n)
    return secs


def build_section(raw, code):
    """Turn a grouped raw section into the final section object (Grimoire schema)."""
    sc = raw['cfg']
    sec = {
        'num': sc.get('num', ''),
        'key': sc['key'],
        'id': sc['id'],
        'title': sc['title'],
        'kind': sc['kind'],
        'group': GROUP,
        'intro': raw['intro'],
        'entries': [],
        'figures': [],
    }
    split = sc.get('split')
    if sc['kind'] == 'faq':
        # The general Q&A is this section's lead: split it into entries (italic
        # question -> roman answer), then append each campaign's Q&A as its own entry.
        assemble.split_qa(sec)
        for n in raw['members']:
            sec['entries'].append({
                'title': n['title'],
                'titleRuns': title_runs_of(n),
                'blocks': n['blocks'],
            })
    elif split == 'term':
        # Definitions: the terms live in the chapter lead (no sub-headings in the PDF).
        lead, entries = split_terms(sec['intro'])
        sec['intro'] = lead
        sec['entries'] = entries
    elif split == 'numbered':
        # Rulings: the numbered clarifications live inside two topic sub-headings the PDF prints
        # ("1. Juego general", "2. Interpretación de las capacidades de las cartas"). Keep that
        # structure — split each sub-heading's prose on its own, and tag every "(N.NN)" entry
        # with its sub-heading as a `group`, so the reader sees the same two parts (the number
        # already carries the topic: 1.x general play, 2.x card-ability interpretation).
        sec['intro'] = list(raw['intro'])
        entries = []
        for n in raw['members']:
            lead, ents = split_numbered(n['blocks'])
            title = (n.get('title') or '').strip()
            if title:
                # A real subsection heading (role='subhead'): the same device the Grimoire uses
                # for "Entornos actual, legado…", so it heads its clarifications in the page, the
                # contents list and the nav, and carries any lead prose the PDF prints under it.
                sub = {'title': title, 'blocks': lead, 'role': 'subhead'}
                if n.get('title_runs'):
                    sub['titleRuns'] = n['title_runs']
                entries.append(sub)
            elif lead:
                sec['intro'].extend(lead)
            entries.extend(ents)
        sec['entries'] = entries
    else:
        for n in raw['members']:
            e = {'title': n['title'], 'blocks': n['blocks']}
            if n.get('title_runs'):
                e['titleRuns'] = n['title_runs']
            sec['entries'].append(e)
    return sec


# ---- links -----------------------------------------------------------------
# ---- the document's own opening ---------------------------------------------
# The FAQ opens on two pages the section parser never reaches: a cover that says what the
# document IS and what is new in this version, and a narrative page carrying the Lovecraft
# epigraph the book chose. Both are the document introducing itself, and dropping them left the
# shelf starting mid-sentence at "Notes and Errata". They are read straight off those two pages —
# by the typography, which both editions set identically: the display face (Teutonic) titles, an
# italic caption gives the version, roman prose describes the document, and a bold lead-in lists
# the new content. Page two's epigraph is the italic block under its display heading.
_DISPLAY = 'teutonic'
_HEAD_SIZE = 15.0


def _lines(page):
    """(y, x, font, size, bold, italic, text) for every printed line, top to bottom."""
    out = []
    for b in page.get_text('dict')['blocks']:
        if 'lines' not in b:
            continue
        for l in b['lines']:
            txt = ''.join(s['text'] for s in l['spans']).strip()
            if not txt:
                continue
            s0 = l['spans'][0]
            font = s0.get('font', '')
            low = font.lower()
            # "ital", not "italic": the embedded name is truncated in these PDFs
            # ("ACaslonPro-SemiboldItali"), and the full word never matched.
            out.append((l['bbox'][1], l['bbox'][0], font, s0.get('size', 0),
                        'bold' in low or 'smbd' in low or 'semibold' in low, 'ital' in low, txt))
    out.sort(key=lambda r: r[0])
    return out


_COLUMN = 150.0            # how far from the title a line may start and still be its column


def _join(lines):
    """Join printed lines into a paragraph, healing the hyphen a line break left behind
    ("añadi- dos" -> "añadidos"), the same way the Grimoire's body parser does."""
    out = ''
    for txt in lines:
        if out.endswith('-') and len(out) > 1 and out[-2].isalpha():
            out = out[:-1] + txt.lstrip()
        else:
            out = (out + ' ' + txt).strip() if out else txt
    return out


def _para(runs_text, bold=False, italic=False):
    return {'type': 'p', 'runs': [{'kind': 'text', 't': runs_text, 'bold': bold,
                                   'italic': italic, 'ref': False}]}


def build_intro(pdf, sc):
    """The cover and the epigraph, as a normal section: lead prose, then the epigraph entry."""
    doc = fitz.open(pdf)
    intro, entries = [], []

    body, newcontent, version = [], '', ''
    for _y, _x, font, _size, bold, italic, txt in _lines(doc[0]):
        if _DISPLAY in font.lower():
            continue                                   # the document's own title; the section has one
        if italic and not version:
            version = txt
        elif bold:
            newcontent = (newcontent + ' ' + txt).strip()
        else:
            body.append(txt)
    if version:
        intro.append(_para(version, italic=True))
    if body:
        intro.append(_para(_join(body)))
    if newcontent:
        intro.append(_para(newcontent, bold=True))

    if doc.page_count > 1:
        rows = _lines(doc[1])
        heads = [r for r in rows if _DISPLAY in r[2].lower() and r[3] >= _HEAD_SIZE]
        title, quote, source = '', [], ''
        if heads:
            # The narrative title is the biggest thing on the page — set over two lines in
            # Spanish, one in English — and the first smaller display heading below it is the
            # next chapter ("Notes and Errata"), which is where the epigraph stops.
            top = max(h[3] for h in heads)
            title = ' '.join(h[6] for h in heads if h[3] == top)
            # Only its own column counts. The English page sets a second column beside the
            # epigraph, and a heading over there ("Campaign Guide Errata") sits higher up the
            # page than the epigraph's last line — so measured by y alone it would cut the
            # attribution off, which is exactly what it did.
            colx = min(h[1] for h in heads if h[3] == top)

            def same_col(x):
                return abs(x - colx) <= _COLUMN

            below = [h[0] for h in heads if h[3] < top and h[0] > heads[0][0] and same_col(h[1])]
            end = min(below) if below else 1e9
            for y, x, _font, _size, _bold, italic, txt in rows:
                if not italic or y >= end or not same_col(x):
                    continue
                if txt[:1] in '-–—':
                    source = txt
                else:
                    quote.append(txt)
        if title and quote:
            blocks = [_para(_join(quote), italic=True)]
            if source:
                blocks.append(_para(source, italic=True))
            entries.append({'title': title.strip(), 'blocks': blocks, 'role': 'epigraph'})

    return {'num': sc.get('num', ''), 'key': sc['key'], 'id': sc['id'], 'title': sc['title'],
            'kind': sc.get('kind', 'rules'), 'group': GROUP, 'intro': intro,
            'entries': entries, 'figures': []}


def grimoire_title_index(gdata):
    """norm(title) -> Grimoire entry id, for every Grimoire entry and section. The FAQ's
    cross-references and auto-links resolve against this, so they always land in the
    Grimoire (the living reference), never inside the retired FAQ."""
    idx = {}
    for s in gdata.get('sections', []):
        for e in s.get('entries', []):
            idx.setdefault(assemble.norm(e['title']), e['id'])
        idx.setdefault(assemble.norm(s['title']), s['id'])
    return idx


def glossary_section(gdata):
    """A deep copy of the Grimoire's glossary section, to feed the auto-linker its
    phrase vocabulary without ever mutating the loaded Grimoire data."""
    for s in gdata.get('sections', []):
        if s.get('kind') == 'glossary':
            return copy.deepcopy(s)
    return None


def count_seticons(sections):
    """How many set/campaign/scenario icons were slotted into the text (for the report)."""
    n = 0
    for s in sections:
        for b in s.get('intro', []):
            n += sum(1 for r in b.get('runs', []) if r.get('kind') == 'seticon')
        for e in s.get('entries', []):
            for r in (e.get('titleRuns') or []):
                if r.get('kind') == 'seticon':
                    n += 1
            for b in e.get('blocks', []):
                n += sum(1 for r in b.get('runs', []) if r.get('kind') == 'seticon')
    return n


# A card reference reads "Name ( <seticon> 20)" — the product mark sits between the parenthesis
# and the number — so the matcher has to see through it. That is cardlinks.link_through_icons,
# shared with the Grimoire, which recovers the same marks with grim_vecicons. Only the pattern
# differs here: the FAQ also prints references carrying several numbers, "( 25, 26)".
_FAQ_REF = re.compile('(' + cardlinks._NAME + r')\s*(\(\s*[\s]*\d+[a-z]?'
                      r'(?:[\s,]*\d+[a-z]?)*[\s]*\))')


def _relink_block(runs, stops):
    return cardlinks.link_through_icons(runs, stops)


# What a card reference's brackets may hold and nothing else: one collection number, or several
# ("( 25, 26)"), or nothing at all when the page prints the mark alone. Anything else in there is
# not a reference — the environments chapter prints "core set <mark> (2016 or 2021)", and reading
# that as a reference moved the mark inside the brackets, between "(" and "2016".
_NUMS_ONLY = re.compile(r'^\s*(\d+[a-z]?(\s*,\s*\d+[a-z]?)*)?\s*$')


def _bracket_text(base, i):
    """The characters between the '(' at `i` and its closing ')'.

    None when this is not a plain bracket at all: something other than a character inside it
    (a game icon), or no closing bracket within a card number's reach."""
    out = []
    for j in range(i + 1, min(i + 26, len(base))):
        if base[j][0] != 'c':
            return None
        if base[j][1] == ')':
            return ''.join(out)
        out.append(base[j][1])
    return None


def _reseat_seticons_runs(runs):
    """Move each inline set icon to the '(' of its card reference. Geometry places almost every
    icon right, but a reference whose card name wraps across a line ("Mercado de los bajos fon-
    dos ( 77)") can strand the icon at the hyphen, or drop it just before the '(' instead of after
    it. Here the icons are lifted out and re-seated, in order, into the reference parentheses of
    the same block — a slot being a parenthesis that holds nothing but a collection number (or
    nothing at all, a bare set-icon reference). Only done when the counts match exactly, so an
    ambiguous block keeps its geometric placement untouched."""
    if not any(r.get('kind') == 'seticon' for r in runs):
        return runs
    atoms = []
    for r in runs:
        if r.get('kind') == 'seticon':
            atoms.append(('s', r.get('fp')))
        elif r.get('kind') == 'text' and 't' in r:
            style = {k: r.get(k, False) for k in ('bold', 'italic', 'ref', 'red')}
            for ch in r['t']:
                atoms.append(('c', ch, style))
        else:
            atoms.append(('o', r))
    fps = [a[1] for a in atoms if a[0] == 's']
    base = [a for a in atoms if a[0] != 's']
    slots = []
    for i, a in enumerate(base):
        if a[0] != 'c' or a[1] != '(':
            continue
        inner = _bracket_text(base, i)
        if inner is not None and _NUMS_ONLY.match(inner):
            slots.append(i + 1)
    if len(slots) != len(fps):
        return runs
    inserts = dict(zip(slots, fps))
    out = []
    for i in range(len(base) + 1):
        if i in inserts:
            out.append(('s', inserts[i]))
        if i < len(base):
            out.append(base[i])
    result = []
    for a in out:
        if a[0] == 'c':
            ch, style = a[1], a[2]
            last = result[-1] if result else None
            if last and last.get('kind') == 'text' and all(last.get(k, False) == style[k] for k in style):
                last['t'] += ch
            else:
                result.append(dict(kind='text', t=ch, **style))
        elif a[0] == 's':
            result.append({'kind': 'seticon', 'fp': a[1]})
        else:
            result.append(a[1])
    return result


def reseat_seticons(sections):
    """Apply _reseat_seticons_runs to every block/title in every section."""
    for s in sections:
        for b in s.get('intro', []):
            b['runs'] = _reseat_seticons_runs(b.get('runs', []))
        for e in s.get('entries', []):
            if e.get('titleRuns'):
                e['titleRuns'] = _reseat_seticons_runs(e['titleRuns'])
            for b in e.get('blocks', []):
                b['runs'] = _reseat_seticons_runs(b.get('runs', []))


def link_cards(sections, pack):
    """ArkhamDB links for "Name ( 20)" card references. Unlike the Grimoire (where card
    refs live only in errata/FAQ), the FAQ names cards throughout — errata, rulings, taboos,
    refractions — so every section is scanned; and the set icon now sitting inside the
    parenthesis is stepped over (see _relink_block / _FAQ_REF)."""
    stops = cardlinks._stops(pack)
    orig_ref = cardlinks._REF
    cardlinks._REF = _FAQ_REF
    n = 0
    try:
        for s in sections:
            for b in s.get('intro', []):
                b['runs'], ch = _relink_block(b.get('runs', []), stops)
                n += ch
            for e in s.get('entries', []):
                if e.get('titleRuns'):
                    e['titleRuns'], ch = _relink_block(e['titleRuns'], stops)
                    n += ch
                for b in e.get('blocks', []):
                    b['runs'], ch = _relink_block(b.get('runs', []), stops)
                    n += ch
    finally:
        cardlinks._REF = orig_ref
    return n


# ---- ids / versions --------------------------------------------------------
def assign_ids(sections):
    used = set()
    for s in sections:
        base = s['id']
        for e in s['entries']:
            eid = f"{base}--{langpack.slugify(e['title'])}"
            k, i = eid, 2
            while k in used:
                k = f'{eid}-{i}'
                i += 1
            used.add(k)
            e['id'] = k


def drop_empty_entries(sections):
    """Drop an entry that has no body at all (and is not a subsection heading). These are stray
    heading fragments — chiefly the icon-reference table titles that survive as an empty node when
    two of them ("Campaign" + "Standalone") get fused by merge_wrapped_headings and so miss the
    icon-word cut in group_sections. A real FAQ entry always carries prose; a subhead may be empty
    on purpose (it heads the entries after it), so those are kept."""
    for s in sections:
        s['entries'] = [e for e in s['entries']
                        if e.get('blocks') or e.get('role') == 'subhead']


def strip_red(sections):
    """The parser tags runs the newest edition printed in red as red=True. The FAQ is
    taken as a single base version (see build()), so there is no diff to draw — drop the
    flag, exactly as apply_versions would when there is only one version."""
    def clean(runs):
        for r in runs:
            r.pop('red', None)
    for s in sections:
        for b in s.get('intro', []):
            clean(b.get('runs', []))
        for e in s.get('entries', []):
            if e.get('titleRuns'):
                clean(e['titleRuns'])
            for b in e.get('blocks', []):
                clean(b.get('runs', []))


# ---- build -----------------------------------------------------------------
def build(pack, grimoire_data):
    """Build the FAQ corpus for one language. `grimoire_data` is that language's already
    -built grimoire_<code>.json (needed so cross-links resolve into the Grimoire).
    Returns (data, report) or (None, None) if the pack declares no FAQ."""
    cfg = faq_cfg(pack)
    if cfg is None:
        return None, None
    pdf = faq_pdf(pack, cfg)
    # Parse WITH the set/campaign/scenario icons recovered from the page's vector art and
    # slotted back into the text (they are invisible to a plain text parse). On the last page the
    # icon-reference TABLES share the paper with the environments prose, so only the marks set
    # inside a sentence are taken there — the tables themselves are rebuilt by extract_iconref.
    doc_pages = fitz.open(pdf).page_count
    nodes, _doc, seticon_svgs = faq_seticons.parse_with_icons(pdf, inline_only_pages=(doc_pages,))
    nodes = merge_wrapped_headings(nodes)

    raw = group_sections(nodes, cfg)
    declared = {sc['id'] for sc in cfg['sections'] if not sc.get('build')}
    found = {r['cfg']['id'] for r in raw}
    for missing in declared - found:
        print(f'  [warn] langs/{pack.code} FAQ: declared section {missing!r} matched no '
              f'heading in the PDF — check its "anchor".')

    sections = [build_section(r, pack.code) for r in raw]

    # The icon-reference chapter: campaign / product / starter / promo icon tables, rebuilt
    # from the last page's vector art (not anchored prose, so built here, appended in place).
    # The document's own opening (cover + epigraph) — read off the first two pages, and put
    # FIRST, so the shelf starts where the document does instead of mid-errata.
    for sc in cfg['sections']:
        if sc.get('build') == 'intro':
            sections.insert(0, build_intro(pdf, sc))

    iconref = 0
    for sc in cfg['sections']:
        if sc.get('build') != 'iconref':
            continue
        groups, isvgs = faq_seticons.extract_iconref(pdf)
        faq_seticons.write_products(isvgs)
        iconref = sum(len(g['items']) for g in groups)
        sections.append({'num': sc.get('num', ''), 'key': sc['key'], 'id': sc['id'],
                         'title': sc['title'], 'kind': 'icons', 'group': GROUP,
                         'intro': [], 'entries': [], 'figures': [], 'groups': groups})

    drop_empty_entries(sections)
    strip_red(sections)
    # Ids before links: the auto-linker reads each entry's id to avoid self-linking.
    assign_ids(sections)

    # Tidy any inline set icon a line-wrap left off its reference parenthesis, before the card
    # linker reads "Name ( <icon> 20)" through those parentheses.
    reseat_seticons(sections)
    # The curated text corrections (see tools/text_fixes.py), before the linkers so a rejoined
    # word can still be matched.
    text_fixes.apply(sections, pack.code)
    # Links: card refs -> ArkhamDB first (so a whole card name is not half-eaten by the
    # glossary auto-linker), then cross-refs and auto-links into the GRIMOIRE.
    cards = link_cards(sections, pack)
    # The references the typographic matcher cannot see — Spanish titles a card in sentence case,
    # so "Mercado de los bajos fondos ( 77)" never looked like a name — found by asking ArkhamDB
    # which card sits at that number; then the exact card behind every reference.
    cards += adb_names.link(sections, pack.code, quiet=True)
    rep = adb_resolve.resolve(sections, pack.code, quiet=True) or {}
    # Report the RESOLVER's own count of references, not the linkers' number of edits: a block
    # holding three references counts once for the linker, so the two are not comparable and
    # printing them side by side read as "more resolved than found".
    refs, direct = rep.get('refs', cards), rep.get('direct', 0)
    # The set/campaign/scenario icons were recovered during the parse (parse_with_icons) and
    # are already inline as `seticon` runs; just write their shared SVG art.
    faq_seticons.write_svgs(seticon_svgs)
    seticons = count_seticons(sections)
    tindex = grimoire_title_index(grimoire_data)
    gloss = glossary_section(grimoire_data)
    links = assemble.linkify(sections, tindex, pack)
    autolink_input = ([gloss] + sections) if gloss else sections
    autolinks = assemble.autolink(autolink_input, tindex, pack)

    versions = [{'v': v['v'], 'date': v['date']} for v in cfg['versions']]
    data = {
        'lang': pack.code,
        'corpus': 'faq1',
        'sections': sections,
        'versions': versions,
        'whatsnew': {},                 # single base version: nothing is "new" yet
        'groupOrder': [GROUP],
    }
    report = {'sections': len(sections),
              'entries': sum(len(s['entries']) for s in sections),
              'cards': refs, 'direct': direct, 'links': links, 'autolinks': autolinks,
              'seticons': seticons, 'seticon_art': len(seticon_svgs), 'iconref': iconref}
    return data, report


def data_path(code):
    return os.path.join(DATA_DIR, f'faq_{code}.json')


def build_and_write(pack, quiet=False):
    """Standalone build: read the already-built grimoire_<code>.json off disk, build the
    FAQ, write data/faq_<code>.json. Returns the report (or None if no FAQ declared)."""
    gpath = pack.data_path
    if not os.path.exists(gpath):
        raise langpack.PackError(
            f'data/grimoire_{pack.code}.json is not built yet — the FAQ links into the '
            f'Grimoire, so build it first with:  python tools/ingest.py {pack.code}')
    with open(gpath, encoding='utf-8') as f:
        gdata = json.load(f)
    data, report = build(pack, gdata)
    if data is None:
        return None
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(data_path(pack.code), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    if not quiet:
        print(f'  faq {pack.code} -> data/faq_{pack.code}.json: {report["sections"]} sections, '
              f'{report["entries"]} entries · {report["cards"]} card references '
              f'({report["direct"]} straight to the card), '
              f'{report["seticons"]} set icons ({report["seticon_art"]} distinct), '
              f'{report["links"]} cross-refs, {report["autolinks"]} auto-links')
    return report


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    packs, errors = langpack.load_valid(sys.argv[1:] or None)
    for code, msg in errors:
        print(f'  BAD {code}: {msg}', file=sys.stderr)
    built = 0
    for p in packs:
        try:
            if build_and_write(p) is not None:
                built += 1
        except langpack.PackError as e:
            print(f'  ERROR {p.code}: {e}', file=sys.stderr)
    print(f'{built} FAQ corpus/corpora built.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
