# -*- coding: utf-8 -*-
"""Link card references — "Name ( collection number)" — to ArkhamDB.

The errata and FAQ chapters name cards as "Name ( 20)": a name and the card's collection
number. ArkhamDB is the community card database and forum, one card search per name in
the reader's language. This wraps each detected name in a search link.

A search, not an exact card id, on purpose: the printed number is a *position* that
repeats across editions (Machete is 20 in the Core Set, the Revised Core, and the 2026
Core), and the product icon that would tell them apart is vector art the text parser
cannot read — so a search, which lists every version, is the honest, version-proof link.

A leading question/function word (Can, What… / Puede, Qué…) is kept out of the link via
the pack's "cardstopwords"; names that genuinely start with an article ("The…") stay
whole because articles are not in that list. English runs a version ahead of the others,
so this simply finds nothing to link in a language whose errata/FAQ are still empty.
"""
import re

_PARTICLE = r"(?:de|del|la|las|los|y|en|a|con|para|por|of|the|and|or|in|on|at|to|from|for|with|von|van)"
_W = r"[\w’‘'.\-]"                     # a card-name word: letters, apostrophes, dot, hyphen
_NAME = r"[A-ZÁÉÍÓÚÜÑ]" + _W + r"*(?:[ ](?:[A-ZÁÉÍÓÚÜÑ]" + _W + r"*|" + _PARTICLE + r"))*"
_REF = re.compile(r"(" + _NAME + r")\s*(\(\s*\d+(?:\s*,\s*\d+)*\s*\))")


def _stops(pack):
    raw = (pack.ui.get('strings', {}) or {}).get('cardstopwords', '')
    return set(w for w in raw.split() if w)


def _split_name(name, stops):
    """'Can Daniela Reyes' -> ('Can ', 'Daniela Reyes'): leading stopwords stay as text,
    the rest becomes the link."""
    words = name.split(' ')
    i = 0
    while i < len(words) - 1 and words[i] in stops:
        i += 1
    lead = (' '.join(words[:i]) + ' ') if i else ''
    return lead, ' '.join(words[i:])


def _merge(runs):
    """Fuse adjacent text runs of the same emphasis so a name split across runs
    ("Hunter" + "'s Instinct") is matched whole. Version-stamped runs are left alone."""
    out = []
    for r in runs:
        p = out[-1] if out else None
        if (r.get('kind', 'text') == 'text' and p and p.get('kind', 'text') == 'text'
                and bool(p.get('bold')) == bool(r.get('bold'))
                and bool(p.get('italic')) == bool(r.get('italic'))
                and not p.get('v') and not r.get('v') and not p.get('red') and not r.get('red')):
            out[-1] = dict(p, t=p.get('t', '') + r.get('t', ''))
        else:
            out.append(r)
    return out


def _link_runs(runs, stops):
    out, changed = [], False
    for r in _merge(runs):
        t = r.get('t', '')
        if r.get('kind', 'text') != 'text' or not t:
            out.append(r); continue
        pos, pieces = 0, []
        for m in _REF.finditer(t):
            lead, link = _split_name(m.group(1), stops)
            if not link:
                continue
            pre = t[pos:m.start()] + lead
            if pre:
                pieces.append(dict(r, t=pre))
            pieces.append({'kind': 'adbcard', 't': link, 'q': link,
                           'bold': bool(r.get('bold')), 'italic': bool(r.get('italic'))})
            pieces.append(dict(r, t=' ' + m.group(2)))       # the " ( 20)" number, kept as text
            pos = m.end()
        if pieces:
            if t[pos:]:
                pieces.append(dict(r, t=t[pos:]))
            out.extend(pieces); changed = True
        else:
            out.append(r)
    return out, changed


# A reference reads "Name ( <icon> 20)" once the product mark between the parenthesis and the
# number has been recovered (faq_seticons / grim_vecicons). The pattern above cannot see past a
# non-text run, so each icon is swapped for a sentinel character the pattern treats as ordinary
# text, the name is linked as usual, and the sentinels become icon runs again afterwards. The
# sentinel is a private-use codepoint: it can never occur in the book's own text.
_ICON_SENT = ''


def link_through_icons(runs, stops):
    """_link_runs, but stepping over the inline set icons inside a reference's parenthesis."""
    conv, style = [], {'bold': False, 'italic': False}
    for r in runs:
        if r.get('kind') == 'seticon':
            conv.append({'kind': 'text', 't': _ICON_SENT, 'bold': style['bold'],
                         'italic': style['italic'], 'ref': False, 'red': False})
        else:
            conv.append(r)
            if r.get('kind') == 'text':
                style = {'bold': r.get('bold', False), 'italic': r.get('italic', False)}
    linked, changed = _link_runs(conv, stops)
    out, icons = [], iter([r for r in runs if r.get('kind') == 'seticon'])
    for r in linked:
        if r.get('kind') == 'text' and _ICON_SENT in r.get('t', ''):
            pieces = r['t'].split(_ICON_SENT)
            for pi, piece in enumerate(pieces):
                if piece:
                    out.append(dict(r, t=piece))
                if pi < len(pieces) - 1:
                    out.append(next(icons))
        else:
            out.append(r)
    return out, changed


def attach(sections, pack):
    stops = _stops(pack)
    n = 0
    for s in sections:
        if not (s.get('key') == 'errata' or s.get('kind') == 'faq'):
            continue
        for b in s.get('intro', []):
            b['runs'], ch = link_through_icons(b.get('runs', []), stops)
            n += ch
        for e in s.get('entries', []):
            if e.get('titleRuns'):
                e['titleRuns'], ch = link_through_icons(e['titleRuns'], stops)
                n += ch
            for b in e.get('blocks', []):
                b['runs'], ch = link_through_icons(b.get('runs', []), stops)
                n += ch
    return {'linked': n} if n else None
