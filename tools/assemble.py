# -*- coding: utf-8 -*-
"""Assemble parsed nodes -> final structured data model for The Living Arkham.
  * groups nodes into top-level sections (ordered, roman-numeral aware)
  * assigns stable slugs/anchors to sections & entries
  * resolves cross-references ("Consulta también ... página N") into inline links
  * attaches rendered figures to image sections
  * validates entry counts & cross-reference integrity

Everything language-specific — the section list, the cross-reference wording, the
auto-link vocabulary, the version history — comes from that language's pack
(langs/<lang>/lang.json). This file knows no language.

Usage:  python tools/assemble.py <lang>
Outputs data/grimoire_<lang>.json plus a validation report.
"""
import json, re, sys, os, unicodedata
from collections import Counter
import langpack, history, ultimatums, reprints, cardlinks, text_fixes
import grim_vecicons, faq_seticons, adb_names, adb_resolve, fanmade
from langpack import slugify

def norm(t):
    t = (t or '').strip().lower().replace('“','"').replace('”','"').replace('’',"'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip(' .:"')

# length-preserving accent fold (positions stay valid in the original string, so
# regex matches on the folded text map straight back onto the source text).
# The 1:1 invariant is enforced in langpack.validate_fold, not just documented.
fold = langpack.fold

def title_variants(title):
    """Splittable forms of an entry title for auto-linking: drop parentheticals and
    quotes, split on ',' and '/'. E.g. 'Agotar, Agotado' -> ['Agotar','Agotado']."""
    t = re.sub(r'\([^)]*\)', ' ', title).replace('“','').replace('”','').replace('"','')
    return [p.strip(' .:') for p in re.split(r'[,/]', t) if p.strip(' .:')]

ROMAN = re.compile(r'^\s*([IVXLC]+)\.\s*(.*)$')

# ---- questions and answers -------------------------------------------------
# The FAQ has no headings, so the parser sees one long chapter lead and the site
# showed it as one: no anchors, no version marks, no place in the index — a wall of
# text. But the chapter IS a list of entries; the book just uses the question as the
# heading. It says so in its own lead: "The entries are presented in a question-and-
# answer format, with the newest questions at the end of the list."
#
# The signal is typographic, not verbal: every question is set in italic and every
# answer in roman. Measured over all three editions, a question is 98.9-100% italic
# and an answer is 0.0% — not one answer contains a single italic character, so any
# threshold between them is the same threshold.
#
# That matters because the words CANNOT be used. English prints "Q:"/"A:"; Spanish
# prints no label at all, so a rule keyed on those letters finds every question in
# English and none in Spanish. The italic finds both.
def _italic_ratio(b):
    """How much of a paragraph is italic, by character. Measured rather than tested
    with any(): a question can carry a non-italic space between two icon glyphs (one
    is 98.9% italic, not 100%), and an answer can carry an italic card name."""
    tot = it = 0
    for r in b['runs']:
        if r.get('kind') != 'text':
            continue
        n = len(r.get('t', '')); tot += n
        if r.get('italic'):
            it += n
    return (it / tot) if tot else 0.0

# A label the book may put in front of a question or an answer: ONE letter and a colon
# or a full stop. English prints "Q:"/"A:", German "F:"/"A:", Italian "D."/"R." on eight
# of its eleven pages and "D:"/"R:" on the other three, Spanish prints nothing. Which
# mark an edition uses is a typesetting habit, so both are accepted — the italic still
# decides what is a question; this only says what to take off the front of it.
#
# Deliberately one letter, not one-or-two: an answer opening "No: you cannot" would
# otherwise be silently inverted into "you cannot". The full-stop form additionally
# requires whitespace after it, or the same rule would eat the "e." of "e.g." and the
# "z." of "z. B."; with it, "e.g." cannot match, because "g" is not whitespace.
QA_LABEL = re.compile(r'^[^\W\d_](?:\s*:\s*|\.\s+)')

def _split_merged_qa(b):
    """A question and its answer that the edition set as ONE paragraph -> the two of
    them; anything else -> the block untouched.

    The German and Italian editions run the answer straight on from the question inside
    a single PDF paragraph — 125 of 144 German pairs, 114 of 130 Italian. Read whole,
    such a paragraph measures only 0.21-0.27 italic, because the roman answer outweighs
    the italic question by length. So split_qa's italic test fails on it, the question
    is never opened as an entry, and the PREVIOUS answer swallows the pair whole: the
    German chapter came out at 39 entries and the Italian at 31, against 144 printed
    questions each.

    The italic is still what decides. The label is only used to locate the seam, and the
    cut is kept ONLY if it does in fact separate an italic question from a roman answer.
    That test is what makes this safe rather than clever: a paragraph that is not a
    merged pair has no seam that passes it and is returned as the same object. English
    (no paragraph carries both labels — measured 0 of 249) and Spanish (no labels at all
    — 0 of 245) therefore cannot reach the rewrite at all.

    The seam falls on a RUN boundary, not inside a run, because the two halves are set in
    different type and the parser already breaks a run where the type changes."""
    runs = b.get('runs') or []
    for i, r in enumerate(runs):
        # not the first run: a block that OPENS with a label is a plain question or a
        # plain answer, and has no seam to find.
        if i == 0 or r.get('kind') != 'text' or r.get('italic'):
            continue
        t = r.get('t', '')
        if not QA_LABEL.match(t.lstrip()):
            continue
        head = {'type': b['type'], 'runs': runs[:i]}
        # the answer's own run may carry the space that separated it from the question
        # ("… ?" + " A: No."); drop it so _strip_label sees the label at the front.
        tail = {'type': b['type'], 'runs': [{**r, 't': t.lstrip()}] + runs[i + 1:]}
        if _italic_ratio(head) >= 0.5 > _italic_ratio(tail):
            return [head, tail]
    return [b]

def _strip_label(runs):
    """Drop the "Q: " label from the first text run, keeping every other run and every
    run property — a red diff mark, a bold word, an icon — exactly as it was."""
    out = []
    done = False
    for r in runs:
        if not done and r.get('kind') == 'text' and r.get('t', '').strip():
            r = dict(r); r['t'] = QA_LABEL.sub('', r['t'], count=1); done = True
        out.append(r)
    return out

def split_qa(sec):
    """A chapter written as alternating italic questions and roman answers is a list
    of entries whose headings happen to be the questions. Rebuilt as real entries, so
    each Q&A gets what every other entry gets: an id, a § anchor, its own line in the
    version history and in the search index, and the red rule down its left when an
    edition rewrites it.

    The question becomes titleRuns, which is a HEADING — and a heading is reused as a
    button in the left nav and as a link in the contents. So it must never contain a
    link of its own: autolink() skips titles for that reason, and the answer restates
    the term anyway. See the autolink() apply loop."""
    lead, groups = [], []
    # First put back apart any pair the edition set as one paragraph (see
    # _split_merged_qa). A no-op wherever no paragraph holds both halves, so the loop
    # below sees exactly what it saw before in every edition that does not do this.
    blocks = [nb for b in sec['intro'] for nb in _split_merged_qa(b)]
    for b in blocks:
        if b['type'] == 'p' and _italic_ratio(b) >= 0.5:
            if groups and not groups[-1]['a']:
                # A question that wrapped into a second italic block — the tail after an inline
                # card reference that broke the paragraph ("…like Amnesia (\\n 96)?") — is a
                # continuation, not a new question. Merge it in; a real new question only ever
                # follows an answer.
                groups[-1]['q'] = {'type': 'p', 'runs': groups[-1]['q']['runs'] + b['runs']}
            else:
                groups.append({'q': b, 'a': []})
        elif groups:
            groups[-1]['a'].append(b)
        else:
            lead.append(b)
    if not groups:
        return                      # a FAQ chapter with no questions yet
    sec['intro'] = lead
    for g in groups:
        runs = _strip_label(g['q']['runs'])
        sec['entries'].append({
            'title': flat_text(runs).strip(),
            'titleRuns': runs,
            'blocks': [{'type': b['type'], 'runs': _strip_label(b['runs'])} for b in g['a']],
        })

# ---- heading numerals ------------------------------------------------------
# A chapter numbers its headings "<numeral>. <text>". An edition can misprint one:
# the ES v1.0 sets the Mythos phase detail heading as "1. Fase de Mitos" two spans
# away from "I. Fase de Mitos" on the same page (p.28) — the same ordinal, spelled
# the other way. Reconciling it changes the NOTATION, never the number.
#
# The evidence is the chapter's own: which notation it mostly uses, and the fact
# that the odd heading has a twin. No word is read, so this holds in any language,
# and a language that does not number its headings never matches.
def attach_table(sec, lang):
    """Hand the rebuilt rows to the entry the table is printed under.

    The book gives the table its own heading, so the parser makes an entry of it — and
    fills that entry with the captions in reading order, which is a jumble. That jumble
    is dropped whether or not the rows were rebuilt, so that every edition of the page
    reads the same way here: history.py re-reads older editions with no images, and if
    the jumble survived in those and not in this one, the table would report itself
    rewritten in whichever edition happens to be newest.

    Which entry is the table's is the pack's to say, for the same reason every other
    string is: this code reads no words. The pack's claim is checked against the page —
    substitution.py reports the heading standing at the top of the art's own column, and
    the two must agree."""
    head = sec.pop('tableHeading', None)
    geom = sec.pop('geomHeading', None)
    rows = sec.pop('table', None)
    if not head:
        raise langpack.PackError(
            f'langs/{lang}/lang.json: section {sec["key"]!r} is "kind": "substitution" '
            f'but declares no "tableHeading", so there is no way to tell which of its '
            f'entries the table is printed under.')
    if geom and norm(geom) != norm(head):
        raise langpack.PackError(
            f'langs/{lang}/lang.json: section {sec["key"]!r} declares its table is headed '
            f'{head!r}, but the heading standing over the art on the page is {geom!r}. '
            f'The declared heading is what picks the entry, so these must agree.')
    for e in sec['entries']:
        if norm(e['title']) == norm(head):
            e['blocks'] = []       # the captions, in reading order: the table's shadow
            if rows:
                e['table'] = rows
            return
    raise langpack.PackError(
        f'langs/{lang}/lang.json: section {sec["key"]!r} declares its table is headed '
        f'{head!r}, but it has no entry by that name '
        f'({", ".join(repr(e["title"]) for e in sec["entries"]) or "no entries at all"}).')


def attach_qr(sec, lang):
    """Hand the QR's link to the entry the book prints the code inside.

    The book runs a sentence that ends in a colon and then prints a QR, because it is
    paper. This is not paper, so the same target becomes a link — but it belongs to that
    sentence's entry and nowhere else, which is why the page is asked (substitution.py
    reports the heading standing over the code) instead of the pack being asked to say.

    Silently dropping it would be the bad outcome: the sentence would end in a colon
    promising something that never arrives."""
    url = sec.pop('qr', None)
    under = sec.pop('qrUnder', None)
    if not url:
        return
    for e in sec['entries']:
        if under and norm(e['title']) == norm(under):
            e['qr'] = url
            return
    raise langpack.PackError(
        f'langs/{lang}/lang.json: section {sec["key"]!r} declares a "qr" link and the page '
        f'prints its code under {under!r}, but the section has no entry by that name. The '
        f'sentence that introduces the link would end in a colon with nothing after it.')


def attach_extras(sec, seclist, lang):
    """Material this language adds that the book does not have.

    The only content on the site that is not the book. It exists because a language can
    have somewhere better to point than the book does — the Spanish edition's own QR goes
    to a generic shop page, while a Spanish community has laid the same sets out with
    extended art — and it is the pack's to declare, which is what keeps it to the packs
    that mean it. English declares none, so English shows none: not a flag in the code,
    just the absence of data.

    It is never mixed into the book's prose. The app fences it off and names the source,
    because a reader has to be able to tell what FFG published from what did not."""
    sc = next((x for x in seclist if x['key'] == sec['key']), None)
    ex = (sc or {}).get('extras')
    if not ex:
        return
    under, items = ex.get('under'), ex.get('items') or []
    if not (under and items and ex.get('source')):
        raise langpack.PackError(
            f'langs/{lang}/lang.json: section {sec["key"]!r} has "extras" but is missing '
            f'"under", "source" or "items". A reader must always be told whose material '
            f'this is and what it hangs off.')
    for e in sec['entries']:
        if norm(e['title']) == norm(under):
            e['extras'] = {'source': ex['source'], 'items': items}
            return
    raise langpack.PackError(
        f'langs/{lang}/lang.json: section {sec["key"]!r} hangs its "extras" under '
        f'{under!r}, but has no entry by that name '
        f'({", ".join(repr(e["title"]) for e in sec["entries"]) or "no entries at all"}).')


HEADNUM = re.compile(r'^\s*([IVXLC]+|\d+)\.\s+(\S.*)$')
_RV = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}

def _roman_to_int(s):
    n = 0
    for i, c in enumerate(s):
        v = _RV[c]
        n += -v if i + 1 < len(s) and _RV[s[i + 1]] > v else v
    return n

def _int_to_roman(n):
    out = ''
    for v, sym in ((100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')):
        while n >= v:
            out += sym; n -= v
    return out

def _headnum(title):
    """-> (ordinal, 'roman'|'arabic', token, rest) for a "<numeral>. <text>" heading,
    else None. A non-canonical roman ("IIII", "VV") is not a numeral the book wrote,
    so it is not one we touch."""
    m = HEADNUM.match(title or '')
    if not m:
        return None
    tok, rest = m.group(1), m.group(2)
    if tok.isdigit():
        return (int(tok), 'arabic', tok, rest)
    n = _roman_to_int(tok)
    if _int_to_roman(n) != tok:
        return None
    return (n, 'roman', tok, rest)

def _renumber_runs(runs, old, new):
    """The rendered title is titleRuns when the edition marked the heading (see
    app.js titleHTML), so the numeral has to be rewritten there too, or the page
    keeps showing the misprint. Only the leading text run can hold it."""
    for r in runs:
        if r.get('kind') != 'text' or not r.get('t'):
            continue
        t = r['t']
        i = t.find(old + '.')
        if i >= 0 and not t[:i].strip():
            r['t'] = t[:i] + new + '.' + t[i + len(old) + 1:]
        return

def normalise_heading_numerals(entries, report=None):
    """Make one chapter's heading numerals agree on a notation.

    Rewrites a heading only when all of these hold:
      * the chapter uses both notations;
      * one notation is used by strictly more headings (a tie is not our call);
      * the odd heading's ordinal AND wording already occur in the dominant
        notation — i.e. it is the same heading printed twice, misnumbered once.

    That last test is the safety bar, and it is why this is honest rather than
    clever: a chapter that legitimately nests arabic sub-steps ("1. Draw a card")
    under roman phases has arabic ordinals that are a subset of the roman ones, and
    dominance alone would wrongly promote them. A sub-step has no identically worded
    roman twin, so the twin test rejects it. A chapter numbered arabic throughout has
    no minority and is left exactly as the book prints it.
    """
    seen = [(e, h) for e in entries for h in [_headnum(e['title'])] if h]
    if not seen:
        return
    counts = Counter(kind for _, (_, kind, _, _) in seen)
    if len(counts) < 2:
        return                                   # one notation: nothing to reconcile
    (dom, dn), (mino, mn) = counts.most_common()
    if dn == mn:
        return                                   # no dominant notation
    twins = {(n, norm(rest)) for _, (n, kind, _, rest) in seen if kind == dom}
    for e, (n, kind, tok, rest) in seen:
        if kind != mino or (n, norm(rest)) not in twins:
            continue
        new = _int_to_roman(n) if dom == 'roman' else str(n)
        old_title = e['title']
        e['title'] = f'{new}. {rest}'
        if e.get('titleRuns'):
            _renumber_runs(e['titleRuns'], tok, new)
        if report is not None:
            report.append((old_title, e['title']))

# ---- phase diagrams --------------------------------------------------------
# The book draws each phase as a flowchart: teal boxes for the numbered steps,
# red ones for the player windows, arrows between them. The parser only sees the
# text inside the boxes, one block per box. It is recognisable by SHAPE, so no
# wording is involved and it works in any language:
#
#   step         a bold lead ending in a number and a colon ("Paso 1.1:" /
#                "Step 1.1:"), followed by the rest of the sentence
#   player window  a block that opens with the game's "free trigger" icon
#   go to        a single bold + italic line ("Pasa a la fase de Enemigos.")
#
# The prose that details the same phase looks nothing like this — its headings are
# a whole bold sentence with no colon — so the two cannot be confused.
STEP_LEAD = re.compile(r'(\d+(?:\.\d+)*)\s*:\s*$')


def _rejoin_step_bodies(blocks):
    """Put a flow box back together where the edition broke it in two.

    A box reads "1.1: Mythos phase begins." — the number bold, the rest plain. Most
    editions set that as one block; the German one splits it, so the sentence arrives as a
    plain block of its own and the chart reads as prose. A plain block straight after a
    step's number is that number's sentence, and nothing else ever is. Returns the same
    list object when there was nothing to rejoin, so the caller can tell."""
    out, changed = [], False
    for b in blocks:
        runs = b.get('runs') or []
        first = runs[0] if runs else None
        plain = (first is not None and first.get('kind') == 'text'
                 and not first.get('bold') and not first.get('italic'))
        prev = out[-1] if out else None
        prev_first = (prev.get('runs') or [None])[0] if prev else None
        prev_is_step = (prev_first is not None and prev_first.get('kind') == 'text'
                        and prev_first.get('bold')
                        and STEP_LEAD.search(prev_first.get('t', '')))
        if plain and prev_is_step and b.get('type') != 'bullet':
            prev['runs'] = list(prev['runs']) + list(runs)
            changed = True
            continue
        out.append(dict(b))
    return out if changed else blocks


def flow_of(entry):
    """-> [{kind, n, i}] describing the entry's blocks as a flowchart, or None."""
    items = []
    for i, b in enumerate(entry['blocks']):
        runs = b.get('runs') or []
        if not runs:
            return None
        first = runs[0]
        if first.get('kind') == 'icon':
            items.append({'kind': 'window', 'i': i})
            continue
        if first.get('kind') != 'text':
            return None
        m = STEP_LEAD.search(first['t']) if first.get('bold') else None
        if m and len(runs) >= 2:
            items.append({'kind': 'step', 'n': m.group(1), 'i': i})
            continue
        # The arrow out of the diagram ("Proceed to the Investigation Phase."). Italic is
        # what marks it; the bold is the English and Spanish editions' habit, and requiring
        # it threw away every Italian diagram at the last box.
        if first.get('italic'):
            items.append({'kind': 'goto', 'i': i})
            continue
        return None
    if sum(1 for it in items if it['kind'] == 'step') < 3:
        return None
    return items


def flow_loops(entry, items):
    """The arrows the book curves back up the right-hand side of a diagram.

    Where they go is written inside the boxes, so it can be read without knowing
    the language:
      * a step that sits right below a player window and names that window loops
        back to it — the label comes from the window box itself, not from a list
        of words;
      * a step that names an EARLIER step's number loops back to that step.
        Direction does the work: a number further down is just the next arrow.

    Checked against the editions' own vector art: these two rules reproduce the
    three loops the book draws, in both languages, with nothing spurious.
    """
    blocks = entry['blocks']

    def flat(i):
        return ''.join(r.get('t', '') for r in blocks[i]['runs'])

    label = None
    for it in items:
        if it['kind'] == 'window':
            label = flat(it['i']).strip().lower()
            break
    num_at = {it['n']: idx for idx, it in enumerate(items) if it.get('n')}
    loops = []
    for idx, it in enumerate(items):
        if it['kind'] != 'step':
            continue
        txt = flat(it['i'])
        if label and idx > 0 and items[idx - 1]['kind'] == 'window' and label in txt.lower():
            loops.append([idx, idx - 1])
        for m in re.finditer(r'\d+(?:\.\d+)+', txt):
            tgt = num_at.get(m.group(0))
            if tgt is not None and tgt < idx:
                loops.append([idx, tgt])
    return loops

def flat_text(runs):
    return ''.join(r.get('t','') for r in runs if r['kind'] == 'text')

def assemble(pack, nodes, images):
    lang = pack.code
    seclist = pack.sections
    by_num = {}
    for idx, s in enumerate(seclist):
        if s['num']: by_num[s['num']] = idx
    started = [False]*len(seclist)
    sections = [None]*len(seclist)
    def mk(idx):
        sc = seclist[idx]
        s = {'num':sc['num'],'key':sc['key'],'id':sc['id'],'title':sc['title'],'kind':sc['kind'],
             'group':sc.get('group'), 'intro':[], 'entries':[], 'figures':[]}
        if sc['kind'] == 'anatomy':
            # rebuilt by card_anatomy.py at render time; only the cards are images
            s['keys'] = images.get('_anatomy') or []
            if not s['keys']:
                # the rebuild found nothing (or was never run): fall back to the
                # page scans, so the chapter is never silently blank
                s['kind'] = 'figures'
        if sc['kind'] == 'icons':
            # rebuilt by icon_reference.py at render time: the groups, their prose, and
            # one row per product. The art is shared, so it is named, not carried.
            built = [b for b in (images.get('_icons') or []) if b.get('key') == sc['key']]
            if built:
                s['groups'] = built[0]['groups']
                s['qr'] = built[0].get('qr')
            else:
                s['kind'] = 'figures'      # never silently blank
        if sc['kind'] == 'substitution':
            # Rebuilt by substitution.py at render time: the table is drawn, and read in
            # reading order its captions are a jumble, so the rows come from the art.
            #
            # This kind never downgrades to 'figures' the way 'anatomy' and 'icons' do.
            # Those chapters ARE their art, so falling back to a scan loses nothing; this
            # page is mostly prose and only its table column is a jumble. Downgrading it
            # would drop that prose — and silently, since history.py re-reads every older
            # edition through here with no images at all (it compares text, not pictures).
            # Every entry would then look like it first appeared in the newest edition.
            s['tableHeading'] = sc.get('tableHeading')
            built = [b for b in (images.get('_subst') or []) if b.get('key') == sc['key']]
            if built:
                s['table'] = built[0]['rows']
                s['geomHeading'] = built[0].get('heading')
                s['qr'] = built[0].get('qr')
                s['qrUnder'] = built[0].get('qrUnder')
        if s['kind'] in ('figures', 'quickref'):
            # quickref keeps its page scan too, as a download — the interactive symbol
            # key the app draws on top is an addition, not a replacement.
            for f in sc.get('figures', []):
                info = images.get(f)
                if info: s['figures'].append({'file':info['file'],'w':info['w'],'h':info['h'],'page':info['page']})
        if s['kind'] == 'quickref':
            # The sheet's text sub-sections (phase sequence, keywords, action types),
            # rebuilt from the page's own left column (quick_reference.py) so their terms
            # can autolink to the glossary. Entries like any other; ids get slugged below.
            for sub in images.get('_quickref', []):
                s['entries'].append({'title': sub['title'], 'blocks': sub['blocks']})
        sections[idx]=s
        return s

    # A placeholder is announced, not written: the site gives it its place in the menu and
    # says it is coming. It backs onto no PDF heading, so it is built up front and marked
    # started — which is not a shortcut but the whole of what it needs, at once:
    #   * "never found" below sees it as found, so the build does not fail;
    #   * the by-name matcher skips started sections, so a real heading can never
    #     wander into it and quietly fill an empty shelf with someone else's chapter;
    #   * with an empty intro it mints no history unit, so it never claims a version.
    # The Ultimatums & Boons viewer is the same: it re-reads the optional-rules chapter
    # (ultimatums.attach, after linking) rather than owning a heading, so it too is built
    # up front and marked started — no page heading may wander in and fill it.
    for idx, sc in enumerate(seclist):
        if sc['kind'] in ('placeholder', 'ultimatums'):
            mk(idx)
            started[idx] = True

    intro_blocks = []
    cur = None            # current section dict
    cur_kind = None

    def match_section(title, level=1):
        m = ROMAN.match(title)
        n = norm(title)
        # The book's alphabetical index closes it: everything after that heading is the
        # index, so the walk stops there. An edition that prints no index says so with an
        # empty "indexStart" and is simply read to the end — the Italian book is one, and
        # without the guard its empty prefix would match the FIRST heading and stop dead.
        index_at = norm(pack.parse['indexStart'])
        if level == 1 and index_at and n.startswith(index_at):
            return 'INDEX'
        # roman numeral exact match to an unstarted section
        if level == 1 and m:
            num = m.group(1)
            if num in by_num and not started[by_num[num]]:
                return by_num[num]
        # numberless specials matched by name (e.g. the quick-reference sheet)
        for idx, sc in enumerate(seclist):
            if started[idx] or sc['num']:      # only numberless / by-name specials here
                continue
            if n.startswith(norm(sc['title'])):
                return idx
        if level != 1:
            # An H2 is a chapter's own subheading and belongs to it as an entry. Only
            # the numberless-by-name branch above may open a section from one, and only
            # for a title the pack asked for by name: the encounter-set variation sheet
            # is set at 16.8pt, one point under a chapter's 18.9pt, so it arrives as an
            # H2 and would otherwise be swallowed whole by the chapter printed above it.
            return None
        # numbered specials matched by name (a book may misprint a numeral: the ES
        # edition labels its "Reimpresiones modificadas" chapter XII twice)
        for idx, sc in enumerate(seclist):
            if started[idx]:
                continue
            if n.startswith(norm(sc['title'])) or norm(sc['title']) in n:
                return idx
        return None

    reached_first = False
    for node in nodes:
        lvl = node['level']; title = node['title']; blocks = node['blocks']
        if lvl <= 2:
            hit = match_section(title, lvl)
            if hit == 'INDEX':
                break
            if isinstance(hit, int):
                if not started[hit]:
                    started[hit] = True
                    cur = mk(hit); cur_kind = cur['kind']
                    # section-start node body -> section intro
                    if blocks:
                        cur['intro'].extend(blocks)
                    reached_first = True
                    continue
        if not reached_first:
            # front matter: capture the "how to use" explanation
            if norm(title).startswith(pack.parse['introStart']) and blocks:
                intro_blocks.extend(blocks)
            elif intro_blocks and blocks and lvl != 1:
                intro_blocks.extend(blocks)
            continue
        # content of current section
        if cur is None:
            continue
        # A wrapped title fragment on a picture page: when the chapter title runs to a
        # second line, that tail is its own L1 node and carries the chapter's intro
        # paragraph — which sits above the art and is NOT picture-page noise. The Spanish
        # "XV. Referencia de iconos de | conjuntos de encuentros" split hit this; the
        # English single-line title captured its intro the ordinary way and never did.
        #
        # Only when the intro is STILL EMPTY, though: that is the whole of the wrapped
        # case (the title's first-line node carried no body, so the intro landed on the
        # fragment). Without that guard this also swallowed every card node of the anatomy
        # chapter — "Lugar revelado", "Plan", "Traición" are all L1 with body — dumping
        # their callout text (card names, traits, numbers) into the intro as prose.
        if (lvl == 1 and blocks and not cur['intro'] and not cur['entries']
                and cur_kind in ('figures', 'anatomy', 'icons', 'quickref')):
            cur['intro'].extend(blocks)
            continue
        if cur_kind in ('figures', 'anatomy', 'icons', 'quickref'):
            # Dense picture-page text: the key, the card names and the numbers are
            # laid out around the art, so read in reading order they are noise. The
            # anatomy and icon chapters get them back properly via card_anatomy.py and
            # icon_reference.py; the quickref sheet redraws its symbol key from the icon
            # list, so its jumble of symbol names is noise too. Here only the section
            # intro already captured survives.
            continue
        if lvl == 1:
            # wrapped banner fragment or stray -> fold body into intro if any
            if blocks:
                cur['intro'].extend(blocks)
            continue
        # lvl 2 or 3 -> an entry (sub-heading). Skip empty titleless.
        if not title:
            continue
        entry = {'title':title, 'blocks':blocks, 'page':node['page']}
        # What the book is doing with this heading: a STOP! callout, the opening of
        # a subsection, or an ordinary entry. Read from the print, not guessed from
        # the type size — the ES edition sets "La regla nefasta" two points larger
        # than its siblings while meaning nothing by it.
        if node.get('role'):
            entry['role'] = node['role']
        if node.get('title_runs'):
            entry['titleRuns'] = node['title_runs']
        cur['entries'].append(entry)
    # A numeral the book misprinted. Per chapter, and necessarily before the ids are
    # slugged from the titles below — and inside assemble(), so history.py sees the
    # same title in every edition it compares and no entry looks newly added.
    renamed = []
    for s in sections:
        if s is not None:
            normalise_heading_numerals(s['entries'], renamed)
    for old, new in renamed:
        print(f'  [numeral] {old!r} -> {new!r}')
    # the phase diagrams: a classification of the blocks, not a copy of them
    for s in sections:
        if s is None:
            continue
        for e in s['entries']:
            fl = flow_of(e)
            if not fl:
                # Try again with each box's text rejoined to its number. The German edition
                # breaks a flow box between the two ("Schritt 1.1:" / "Mythosphase beginnt."
                # as two blocks), which is a plain block in the middle of the diagram and
                # ended the whole chart — all four German phase diagrams came out as prose.
                # Only kept if the rejoin actually yields a diagram, so an entry that is
                # really prose is never rewritten.
                merged = _rejoin_step_bodies(e['blocks'])
                fl = flow_of({'blocks': merged}) if merged is not e['blocks'] else None
                if fl:
                    e['blocks'] = merged
            if fl:
                e['flow'] = fl
                lp = flow_loops(e, fl)
                if lp:
                    e['loops'] = lp
    # A section the parser never found is silently absent from the site, which is
    # the worst way to fail: the run "succeeds" and the chapter is just gone.
    missing = [seclist[i] for i in range(len(seclist)) if not started[i]]
    if missing:
        want = ', '.join(f'{s["num"] + ". " if s["num"] else ""}{s["title"]}' for s in missing)
        raise langpack.PackError(
            f'langs/{lang}/lang.json: {len(missing)} of {len(seclist)} sections were never '
            f'found in {pack.current["pdf"]}:\n    {want}\n'
            f'  A section is matched by its roman numeral ("I.", "II.", …) or by its "title" '
            f'matching the heading printed in the PDF.\n'
            f'  See the headings your PDF actually has:\n'
            f'    python tools/inspect_pdf.py {lang} --sections')
    sections = [s for s in sections if s]
    # The FAQ's questions become entries. Here, and not in main(), because history.py
    # re-parses every edition through assemble() — so this is what lets each question
    # carry the edition that answered it, instead of the whole chapter carrying one
    # "something changed" stamp. After the numerals and the diagrams (a question is
    # neither), and before the ids, so questions are slugged like everything else.
    for s in sections:
        if s['kind'] == 'faq':
            split_qa(s)
    for s in sections:
        if s['kind'] == 'substitution':
            attach_table(s, lang)
            attach_qr(s, lang)
    # extras is not a substitution feature — any section may add community material. Its
    # own loop, so a pack that declares extras elsewhere is honoured (and a bad "under"
    # still raises loudly) instead of being silently ignored.
    for s in sections:
        attach_extras(s, seclist, lang)
    # assign entry ids (unique within language)
    used = set()
    title_index = {}       # norm(title) -> entry id
    for s in sections:
        base = s['id']
        for e in s['entries']:
            eid = slugify(e['title'])
            full = f'{base}--{eid}'
            k = full; i = 2
            while k in used:
                k = f'{full}-{i}'; i += 1
            used.add(k)
            e['id'] = k
            title_index.setdefault(norm(e['title']), k)
    for s in sections:
        order_phase_pairs(s)
    # attach montage figures (example card-art resources) to their glossary entries
    entry_by_title = {}
    for s in sections:
        for e in s['entries']:
            entry_by_title.setdefault(norm(e['title']), e)
    for m in pack.montages:
        e = entry_by_title.get(norm(m['entry']))
        info = images.get(m['name'])
        if e is None or not info:
            print(f'  [warn] montage {m["name"]!r} not attached (entry={m["entry"]!r} found={e is not None} img={info is not None})')
            continue
        e.setdefault('figures', []).append({
            'file': info['file'], 'w': info['w'], 'h': info['h'],
            'srcpage': m.get('srcpage', info.get('page')), 'alt': m['alt'], 'info': m['info']})
    # re-insert standalone symbols (drawn as vectors, invisible to the text parser)
    for ins in pack.inline_symbols:
        e = entry_by_title.get(norm(ins['entry']))
        if e is None:
            print(f'  [warn] inline symbol: entry {ins["entry"]!r} not found'); continue
        anchor = norm(ins['after']); idx = None
        for i, b in enumerate(e['blocks']):
            if norm(flat_text(b['runs'])).endswith(anchor):
                idx = i; break
        if idx is None:
            print(f'  [warn] inline symbol: anchor {ins["after"]!r} not found in {ins["entry"]!r}'); continue
        e['blocks'].insert(idx+1, {'type':'sym', 'runs':[{'kind':'icon','name':ins['icon']}]})
    intro_section = {'num':'','key':'intro','id':'intro','title':pack.parse['introTitle'],
                     'kind':'intro','intro':intro_blocks,'entries':[],'figures':[]}
    return intro_section, sections, title_index

def linkify(sections, title_index, pack):
    trig = re.compile(pack.patterns['trigger'], re.I)
    pageword = pack.patterns['pageWord']
    pageref = re.compile(pack.patterns['pageRef'], re.I)
    # A cross-reference names its target in quotes, and each edition uses its own marks:
    # English and Italian "…", Spanish «…», German „…“ — whose OPENING mark (U+201E) is a
    # different character from every other edition's, which is why German found none at all.
    # Being permissive costs nothing: a match only becomes a link if the quoted words are
    # actually a heading in this book's own index.
    quote = re.compile(r'([“"„«‹])(.+?)([”"“»›])')
    linkcount = [0]
    def process_run(run, ctx_has_trig):
        """Split a text run into inline runs at cross-ref titles (links) and
        page references ('en la página 13' -> a pageref chip)."""
        if run['kind'] != 'text':
            return [run]
        t = run['t']
        v = run.get('v')
        repls = []                                        # (start, end, newrun)
        for m in quote.finditer(t):
            key = norm(m.group(2)); tgt = title_index.get(key)
            if not tgt:
                continue
            after = t[m.end():m.end()+28]; before = t[max(0, m.start()-45):m.start()]
            if not (ctx_has_trig or re.search(pageword, after, re.I) or trig.search(before)):
                continue
            lk = {'kind':'link','t':m.group(0),'target':tgt,
                  'bold':run.get('bold',False),'italic':run.get('italic',False)}
            if v: lk['v'] = v
            repls.append((m.start(), m.end(), lk)); linkcount[0]+=1
        if ctx_has_trig:
            for m in pageref.finditer(t):
                repls.append((m.start(), m.end(), {'kind':'pageref','n':re.sub(r'\s+','',m.group(1))}))
        if not repls:
            return [run]
        repls.sort(key=lambda x: x[0])
        out = []; last = 0
        for st, en, nr in repls:
            if st < last:
                continue                                  # skip overlaps
            if st > last:
                out.append({**run, 't': t[last:st]})
            out.append(nr); last = en
        if last < len(t):
            out.append({**run, 't': t[last:]})
        return out
    def process_blocks(blocks):
        for b in blocks:
            ctx = trig.search(flat_text(b['runs'])) is not None
            newruns = []
            for r in b['runs']:
                newruns.extend(process_run(r, ctx))
            b['runs'] = newruns
    for s in sections:
        process_blocks(s['intro'])
        for e in s['entries']:
            process_blocks(e['blocks'])
    return linkcount[0]


def autolink(sections, title_index, pack):
    """Turn the first mention of a related glossary term into an inline link, so the
    reader can jump straight to it (e.g. 'Robar 1 carta' -> the 'Robar cartas' entry).
    Conservative on purpose: glossary only, distinctive terms + curated aliases,
    first occurrence per target per entry, never self-links, capped per entry."""
    al = pack.autolink
    # the lists are matched against accent-folded text, so fold them on load:
    # a pack may spell them either way ('aparición' or 'aparicion') and mean the same.
    stop = {fold(x) for x in al.get('stop', [])}
    allow1 = {fold(x) for x in al.get('allowSingleWord', [])}
    cap = al.get('cap', 12)
    phrases = {}                                   # folded phrase -> target id
    def add(phrase, tgt, force=False):
        f = fold(re.sub(r'\s+', ' ', phrase).strip(' .:'))
        if not f or (f in stop and not force):
            return
        if not force and (len(f) < 3 or (len(f.split()) == 1 and f not in allow1)):
            return
        phrases.setdefault(f, tgt)
    for s in sections:
        if s.get('kind') != 'glossary':
            continue
        for e in s['entries']:
            for pv in title_variants(e['title']):
                add(pv, e['id'])
    for alias, tgt_title in al.get('alias', {}).items():
        tid = title_index.get(norm(tgt_title))
        if tid:
            add(alias, tid, force=True)
        else:
            print(f'  [warn] autolink alias target not found: {tgt_title!r} '
                  f'(check "autolink.alias" in langs/{pack.code}/lang.json — the value must be '
                  f'a glossary entry title exactly as printed)')
    if not phrases:
        return 0
    tgt_of = dict(phrases)
    # longest phrases first so 'cartas de apoyo' wins over any shorter overlap
    alt = '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    rx = re.compile(r'(?<![0-9a-z])(' + alt + r')(?![0-9a-z])')
    count = [0]
    def process_group(group, e, used, n_here):
        """Match across a run of consecutive text runs (a phrase like 'Robar 1 carta'
        may be split by bold formatting), then rebuild preserving original formatting
        outside the matched spans."""
        text = ''.join(r['t'] for r in group); ft = fold(text)
        spans = []; pos = 0                        # char span -> source run
        for r in group:
            spans.append((pos, pos + len(r['t']), r)); pos += len(r['t'])
        def run_at(p):
            for rs, re_, r in spans:
                if rs <= p < re_: return r
            return group[-1]
        repls = []
        for m in rx.finditer(ft):
            tgt = tgt_of.get(m.group(1))
            if not tgt or tgt == e['id'] or tgt in used or n_here[0] >= cap:
                continue
            st, en = m.start(1), m.end(1); base = run_at(st)
            lk = {'kind': 'link', 't': text[st:en], 'target': tgt}
            if base.get('bold'):   lk['bold'] = True
            if base.get('italic'): lk['italic'] = True
            if base.get('v'):      lk['v'] = base['v']
            repls.append((st, en, lk)); used.add(tgt); n_here[0] += 1; count[0] += 1
        if not repls:
            return group
        out = []; last = 0
        def emit_plain(a, b):
            for rs, re_, r in spans:
                lo = max(a, rs); hi = min(b, re_)
                if lo < hi: out.append({**r, 't': text[lo:hi]})
        for st, en, lk in repls:
            if st > last: emit_plain(last, st)
            out.append(lk); last = en
        if last < len(text): emit_plain(last, len(text))
        return out
    def process_entry(e):
        used = set()                               # targets already linked in this entry
        for b in e['blocks']:
            for r in b['runs']:
                if r.get('kind') == 'link' and r.get('target'):
                    used.add(r['target'])          # don't duplicate an existing see-also link
        n_here = [0]
        for b in e['blocks']:
            newruns = []; runs = b['runs']; i = 0
            while i < len(runs):
                if runs[i].get('kind') != 'text':
                    newruns.append(runs[i]); i += 1; continue
                j = i
                while j < len(runs) and runs[j].get('kind') == 'text': j += 1
                newruns.extend(process_group(runs[i:j], e, used, n_here)); i = j
            b['runs'] = newruns
    # Which chapters carry auto-links is a property of the chapter's KIND, not of its
    # key: the glossary cross-links within itself, and the rules chapters link out to
    # the glossary that defines their vocabulary. Kind is already in every pack, so a
    # new language gets this for free — a list of section keys would have to be
    # repeated per pack and would link nothing, silently, once it drifted.
    # A chapter's lead text is prose like any entry, and in the chapters the book
    # writes as one continuous procedure (setup, initiation, skill tests) it IS the
    # whole chapter: the parser only makes an entry where it finds a sub-heading, and
    # those chapters have none. Scoped as its own unit, so the cap and the
    # first-mention rule read per chapter-lead rather than being spent on whichever
    # entry happened to come first.
    for s in sections:
        if s.get('kind') not in ('glossary', 'rules', 'faq', 'quickref'):
            continue
        if s['intro']:
            process_entry({'id': s['id'], 'blocks': s['intro']})
        for e in s['entries']:
            # Not the flow diagrams. Inside a box, a teal dotted mark already means
            # "another step of this diagram", and a glossary link is drawn the same
            # way but leaves the chapter entirely — two identical marks, two opposite
            # destinations, in boxes eight words long. The prose that details the very
            # same phase sits on the same page and is linked, so nothing is lost.
            if e.get('flow'):
                continue
            # Nor the epigraph a document opens with. It is a quotation from a story, not
            # rules text: turning "revelación" in a line of Lovecraft into a link to the
            # glossary reads as a mistake, and the term is not being used in its game sense
            # there at all.
            if e.get('role') == 'epigraph':
                continue
            process_entry(e)
    # The card-anatomy key defines the parts of a card in the glossary's own
    # vocabulary ("the difficulty of a skill test to investigate this location"),
    # so it is the one place outside the glossary worth linking. Each item is a
    # self-contained definition, so each is scoped on its own — otherwise only the
    # first of the eighteen could ever mention "skill test".
    for s in sections:
        for k in s.get('keys', []):
            for it in k['items']:
                blk = {'runs': it['desc']}          # process_entry rebuilds blk['runs']
                process_entry({'id': k['id'], 'blocks': [blk]})
                it['desc'] = blk['runs']
    return count[0]


def apply_versions(allsecs, pack, added=None, changed=None):
    """Stamp each entry with its history, and tag the text the newest edition added.

    `added` / `changed` come from history.build(), which compares the editions
    themselves. That comparison is the only trustworthy source for "is this entry
    new": the red heading the publisher prints means "something in here changed",
    and in the English v1.1 thirteen of the fourteen red headings sit on entries
    that already existed in v1.0.

    The red *runs* remain exactly right for "which words are new", so they become
    `v` marks on the runs of the newest edition.
    """
    versions = [{'v': v['v'], 'date': v['date']} for v in pack.versions]
    latest = versions[-1]['v'] if len(versions) > 1 else None
    added = added or {}
    changed = changed or {}

    def tag(runs):
        for r in runs:
            if r.pop('red', False) and latest:
                r['v'] = latest

    def stamp(obj, uid):
        a = added.get(uid)
        ch = changed.get(uid, [])
        if a:
            obj['addedIn'] = a
        if ch:
            obj['changedIn'] = ch

    for s in allsecs:
        for b in s.get('intro', []):
            tag(b['runs'])
        stamp(s, history.SEC + s['id'])       # the chapter's own lead text
        # the rebuilt card-anatomy key is prose like any other: it gets the same
        # diff marks, and — either way — loses the parser's private `red` flag
        for k in s.get('keys', []):
            for it in k['items']:
                tag(it['term'])
                tag(it['desc'])
        for e in s.get('entries', []):
            if e.get('titleRuns'):
                tag(e['titleRuns'])
            for b in e['blocks']:
                tag(b['runs'])
            stamp(e, e['id'])
    return versions, history.whatsnew_index(allsecs, added, changed, versions)


def order_phase_pairs(sec):
    """Put the prose before the diagram in every phase of "Timing and Gameplay".

    A DELIBERATE departure from the printed page. Each phase of that chapter is a pair of
    entries under one heading — the written rules, and the flow diagram of the same phase —
    and the book sets them prose-then-diagram for phases I, II and III but diagram-then-prose
    for IV, purely because of how the page broke. On a screen there is no page to break, and
    the inconsistency reads as a mistake: the reader who has learnt "text, then picture" three
    times over is thrown by the fourth. So the pair is put back in the book's own dominant
    order. Ids are already assigned, so each entry keeps its anchor and its place in the
    version history; only the reading order changes."""
    ents = sec.get('entries') or []
    for i in range(len(ents) - 1):
        a, b = ents[i], ents[i + 1]
        if a.get('flow') and not b.get('flow') and a['title'] == b['title']:
            ents[i], ents[i + 1] = b, a


def finalize(pack, allsecs, title_index):
    """Everything after the sections are grouped: version history, cross-links,
    auto-links, the Ultimatums & Boons viewer, and the assembled data dict. Shared
    by main() and tools/ingest.py so the two build paths can never drift apart —
    each used to carry its own copy, and one had already fallen a step behind.
    Returns (data, report)."""
    # The history is not optional decoration: skipping it here would quietly
    # rewrite the data file with every addedIn/changedIn stripped out.
    added = changed = None
    if len(pack.versions) > 1:
        newest = {}
        for s in allsecs:
            # The quick-reference sheet is left out of history's diff on purpose: its
            # entries only exist when the PDF is open, so the imageless re-read of an older
            # edition could never find them and would brand every one "new" in the latest.
            # Its version info is read from the page's own marks instead, just below.
            if s.get('kind') == 'quickref':
                continue
            if s.get('intro'):
                newest[history.SEC + s['id']] = {'blocks': s['intro']}
            for e in s.get('entries', []):
                newest[e['id']] = e
        added, changed, _parsed, notes = history.build(pack, newest_units=newest)
        for n in notes:
            print(f'  [note] {n}')
        # The reference sheet is foundational — present since the first edition, so never
        # "new" — but the publisher DOES print its reworded lines red, exactly as in the
        # chapters. So read its history straight off those marks: added in the first
        # edition, changed in the latest wherever a run is red. This runs before
        # apply_versions, which consumes the red flag (turning it into the inline "new"
        # highlight) and feeds these same dicts to the What's New index — so the sheet's
        # update shows both as a badge and in the changelog, like every other chapter.
        first, last = pack.versions[0]['v'], pack.versions[-1]['v']
        for s in allsecs:
            if s.get('kind') != 'quickref':
                continue
            for e in s.get('entries', []):
                added.setdefault(e['id'], first)
                if any(r.get('red') for b in e['blocks'] for r in b['runs']):
                    changed.setdefault(e['id'], []).append(last)
    versions, whatsnew = apply_versions(allsecs, pack, added, changed)
    # The curated text corrections go here: AFTER the edition diff, so a correction never reads as
    # the newest edition having rewritten the entry; BEFORE the linkers, so a word we just rejoined
    # ("Ju gador" -> "Jugador") can still be matched and linked.
    text_fixes.apply(allsecs, pack.code)
    # The product marks the book draws INSIDE its sentences — the five investigator decks named
    # in the optional rules, and the mark inside every "Name ( 20)" — are vector art the text
    # parse cannot see, so they are scanned off the page and slotted back in here (see
    # tools/grim_vecicons.py). Before the card linker, which then reads straight through them.
    vicons, vsvgs = grim_vecicons.scan(pack.pdf, quiet=True)
    faq_seticons.write_svgs(vsvgs)
    grim_vecicons.attach(allsecs, vicons)
    # Card references in the errata/FAQ ("Name ( 20)") -> ArkhamDB. Before the auto-linker, so a
    # card name like "Hunter's Instinct" is claimed whole here and not half-eaten by the glossary
    # auto-link matching the keyword "Hunter" inside it. Three steps: the typographic matcher,
    # then the ones only ArkhamDB's own card list can recognise, then the exact card each names.
    cardlinks.attach(allsecs, pack)
    adb_names.link(allsecs, pack.code)
    adb_resolve.resolve(allsecs, pack.code)
    links = linkify(allsecs, title_index, pack)
    autolinks = autolink(allsecs, title_index, pack)
    # The Ultimatums & Boons viewer reads its items out of the optional-rules chapter, so
    # it runs last: after the chapter's runs have been linked, version-stamped and slugged,
    # so a card's rule keeps its cross-references and carries none of the diff bookkeeping.
    # The cross-language fill (missing cards shown in English) is a separate step, run once
    # every language is built — tools/ub_merge.py.
    ub = ultimatums.attach(allsecs, pack)
    # The community's deeper skill-test timing reference, as a second view of that chapter.
    fanmade.attach(allsecs, pack.code)
    # The Modified Reprints chapter's two-column list, recovered into a clean table.
    rp = reprints.attach(allsecs, pack)
    data = {'lang': pack.code, 'sections': allsecs, 'versions': versions, 'whatsnew': whatsnew,
            'groupOrder': list(langpack.SECTION_GROUPS)}
    return data, {'links': links, 'autolinks': autolinks, 'versions': versions,
                  'whatsnew': whatsnew, 'ub': ub, 'reprints': rp}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/assemble.py <lang>', file=sys.stderr)
        return 2
    pack = langpack.load(sys.argv[1])
    lang = pack.code
    if not os.path.exists(pack.nodes_path):
        raise langpack.PackError(
            f'the parsed nodes for "{lang}" are missing (data/_nodes_{lang}.json).\n'
            f'  Run the whole pipeline instead:  python tools/ingest.py {lang}')
    nodes = json.load(open(pack.nodes_path, encoding='utf-8'))
    images_path = pack.images_path(os.path.join(langpack.ROOT, 'assets', 'img'))
    if not os.path.exists(images_path) and (pack.figures or pack.montages):
        # Without the manifest every figure would quietly vanish from the page while
        # the run still reported success — so refuse rather than half-build.
        raise langpack.PackError(
            f'the figure manifest for "{lang}" is missing '
            f'(assets/img/images_{lang}.json), but the pack declares '
            f'{len(pack.figures)} figure(s) and {len(pack.montages)} montage(s).\n'
            f'  Render them first:  python tools/render_images.py {lang}\n'
            f'  Or just run the whole pipeline:  python tools/ingest.py {lang}')
    images = json.load(open(images_path, encoding='utf-8')) if os.path.exists(images_path) else {}
    intro, sections, title_index = assemble(pack, nodes, images)
    allsecs = [intro] + sections
    data, rep = finalize(pack, allsecs, title_index)
    json.dump(data, open(pack.data_path, 'w', encoding='utf-8'), ensure_ascii=False)
    links, autolinks, versions, whatsnew, ub = (
        rep['links'], rep['autolinks'], rep['versions'], rep['whatsnew'], rep['ub'])
    # ---- report ----
    print(f'[{lang}] sections: {len(allsecs)}  cross-links: {links}  auto-links: {autolinks}  versions: {[v["v"] for v in versions]}')
    for v, wn in whatsnew.items():
        print(f'  what\'s new in v{v}: {len(wn["new"])} new entries, {len(wn["updated"])} updated')
    if len(versions) > 1 and not whatsnew:
        print(f'  [warn] v{versions[-1]["v"]} produced no "What\'s New" entries. That diff comes '
              f'from the dark-red text the publisher prints for additions; if this edition does '
              f'not use red, the section will not appear.')
    tot = sum(len(s['entries']) for s in allsecs)
    print(f'  TOTAL entries: {tot}')
    if ub:
        print(f'  ultimatums viewer: {ub["ultimatums"]} ultimatum(s), {ub["boons"]} boon(s), '
              f'{ub["refractions"]} refraction(s)'
              + (f'  [{len(ub["textonly"])} text-only, no art: {", ".join(ub["textonly"])}]'
                 if ub['textonly'] else ''))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
