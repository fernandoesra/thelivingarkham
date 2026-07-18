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
import faq_seticons

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


def split_numbered(blocks):
    """Rulings: a paragraph opening with a bold '(N.NN)' is a clarification. Its bold lead is
    the heading; the rest of that paragraph and the blocks under it are the body."""
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
        # Rulings: the numbered clarifications live inside the two topic sub-headings; pool
        # their prose and split it, so each "(N.NN)" becomes its own entry (the number keeps
        # the topic: 1.x is general play, 2.x is card-ability interpretation).
        pooled = []
        for n in raw['members']:
            pooled.extend(n['blocks'])
        lead, entries = split_numbered(pooled)
        sec['intro'] = raw['intro'] + lead
        sec['entries'] = entries
    else:
        for n in raw['members']:
            e = {'title': n['title'], 'blocks': n['blocks']}
            if n.get('title_runs'):
                e['titleRuns'] = n['title_runs']
            sec['entries'].append(e)
    return sec


# ---- links -----------------------------------------------------------------
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


# A card reference now reads "Name ( <seticon> 20)" — the set icon was slotted between the
# parenthesis and the number. So the ArkhamDB matcher must see through that icon: the seticon
# runs are swapped for a sentinel char the pattern treats as whitespace, the card name is
# linked as usual, and the sentinels are turned back into seticon runs afterwards.
_SENT = ''
_FAQ_REF = re.compile('(' + cardlinks._NAME + r')\s*(\(\s*[\s]*\d+[a-z]?'
                      r'(?:[\s,]*\d+[a-z]?)*[\s]*\))')


def _relink_block(runs, stops):
    conv, style = [], {'bold': False, 'italic': False}
    for r in runs:
        if r.get('kind') == 'seticon':
            conv.append({'kind': 'text', 't': _SENT, 'bold': style['bold'],
                         'italic': style['italic'], 'ref': False, 'red': False})
        else:
            conv.append(r)
            if r.get('kind') == 'text':
                style = {'bold': r.get('bold', False), 'italic': r.get('italic', False)}
    linked, changed = cardlinks._link_runs(conv, stops)
    out, fps = [], iter([r['fp'] for r in runs if r.get('kind') == 'seticon'])
    for r in linked:
        if r.get('kind') == 'text' and _SENT in r.get('t', ''):
            pieces = r['t'].split(_SENT)
            for pi, piece in enumerate(pieces):
                if piece:
                    out.append(dict(r, t=piece))
                if pi < len(pieces) - 1:
                    out.append({'kind': 'seticon', 'fp': next(fps)})
        else:
            out.append(r)
    return out, changed


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
    # slotted back into the text (they are invisible to a plain text parse). The last page —
    # the icon-reference tables — is left to extract_iconref, so its icons are not also
    # injected into the environments prose that shares it.
    doc_pages = fitz.open(pdf).page_count
    nodes, _doc, seticon_svgs = faq_seticons.parse_with_icons(pdf, skip_pages=(doc_pages,))
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

    strip_red(sections)
    # Ids before links: the auto-linker reads each entry's id to avoid self-linking.
    assign_ids(sections)

    # Links: card refs -> ArkhamDB first (so a whole card name is not half-eaten by the
    # glossary auto-linker), then cross-refs and auto-links into the GRIMOIRE.
    cards = link_cards(sections, pack)
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
              'cards': cards, 'links': links, 'autolinks': autolinks,
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
              f'{report["entries"]} entries · {report["cards"]} card links, '
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
