# -*- coding: utf-8 -*-
"""Rebuild the card-anatomy chapter from the PDF's own vector art.

The book draws this chapter as a picture: a card, numbered diamonds around it, a
teal arrow curving from each diamond to the exact spot it means, and a key that
explains the numbers. Shipping it as a page scan makes the text unselectable,
unsearchable, untranslatable and invisible to a screen reader. So it is read
back out and rebuilt: only the card stays a picture.

Nothing here knows a language or a page layout. Everything is found by shape,
which matters more than it sounds: the Spanish edition spreads this chapter over
four portrait pages and the English one compresses it onto two-page spreads, yet
both are read by the same rules (see `tools/README.md`).

  card      a rounded rect (4 corner curves + 4 sides) with a light fill
  arrow     a fat teal Bezier + a teal triangle; the triangle's apex is the point
  diamond   a big Teutonic number set beside the arrow's tail
  key panel a pale rect holding "N. Term: description" items

The arrow is what carries the meaning, and it is the one thing the page scan
threw away. Its apex, expressed as a percentage of the card, is the marker.
"""
import re
import math
import itertools

import fitz

import parse_grimoire as pg

TEAL = (0.19, 0.387, 0.374)   # editions print it a shade apart -> matched by range
LEAD = re.compile(r'^(\d+)\.\s*')
ROMAN = re.compile(r'^[IVXLCDM]+\.\s')          # "VII. Card Anatomy" is the chapter, not a card


def _sig(d):
    """The shape of a path, as the letters of its segments: 'clclclcl' is a rounded rect."""
    return ''.join(i[0] for i in d['items'])


def _near(c, ref, tol=.06):
    return c is not None and len(c) == len(ref) and all(abs(a - b) < tol for a, b in zip(c, ref))


def _verts(items):
    pts = []
    for it in items:
        for p in it[1:]:
            if isinstance(p, fitz.Point):
                pts.append((round(p.x, 2), round(p.y, 2)))
    out = []
    for p in pts:
        if not any(math.dist(p, q) < .5 for q in out):
            out.append(p)
    return out


def _apex(tri):
    """An arrowhead's point: the vertex opposite its shortest side (the base)."""
    if len(tri) != 3:
        return None
    ij = min(itertools.combinations(range(3), 2), key=lambda k: math.dist(tri[k[0]], tri[k[1]]))
    return tri[({0, 1, 2} - set(ij)).pop()]


def cards_on(page):
    """The card faces: a rounded rect big enough to be a card."""
    return [d['rect'] for d in page.get_drawings()
            if d['type'] == 'f' and _sig(d) == 'clclclcl' and d['rect'].get_area() > 3000]


def arrows_on(page):
    """[{apex, tail}] — the pointer arrows, in page points."""
    dr = page.get_drawings()
    shafts = [d for d in dr if d['type'] == 's' and (d.get('width') or 0) > 3
              and _near(d.get('color'), TEAL)]
    heads = [d for d in dr if d['type'] == 'f' and _near(d.get('fill'), TEAL) and _sig(d) == 'lll']
    out = []
    for h in heads:
        apex = _apex(_verts(h['items']))
        if apex is None:
            continue
        best, bd = None, 1e9
        for s in shafts:
            it = s['items'][0]
            ends = [(it[1].x, it[1].y), (it[-1].x, it[-1].y)]
            for e in ends:
                d = math.dist(e, apex)
                if d < bd:
                    bd, best = d, ends
        if best is None:
            continue
        out.append({'apex': apex, 'tail': max(best, key=lambda e: math.dist(e, apex))})
    return out


# An arrow is drawn as one self-contained block of the page's content stream:
#
#   q 1 0 0 1 418.6568 536.424 cm 5 w 4 M 0 0 m -19.8 -.288 ... 24.48 c S Q
#   q 1 0 0 1 429.9664 536.5885 cm 5 w 4 M 0 0 m -19.373 -7.37 l ... l h f Q
#
# The `cm` translate is where the path starts, which for these is the arrow's own
# end point — the very thing already located above. So the blocks are matched by
# geometry, not by their text, and nothing else in the stream is touched. The
# pattern only has to be loose enough to find the blocks; the coordinates decide.
#
# (Redaction is the obvious tool and does not work here: MuPDF does not count
# these paths as covered by a rect of their own size, and a redaction would also
# paint over the card art underneath, which is the thing being kept.)
_BLOCK = re.compile(rb'q\s+1 0 0 1 (-?[\d.]+) (-?[\d.]+) cm[^qQ]*?[Sf]\s*Q\s*')
CREAM = (0.932, 0.909, 0.843)     # the diamond's parchment fill


def _xobj_re(name):
    return re.compile(rb'q[^qQ]*?/' + re.escape(name) + rb' Do\s*Q\s*')


def _decor_rects(page):
    """The numbered diamonds: a parchment quad over a dark shadow. They are drawn
    half over the card — the book tucks them under its edge — so they have to go
    with the arrows, or the card keeps a bite out of it. They are rebuilt as
    markers anyway.

    The card's own printed border is a dark rect too, so it is told apart by the
    one thing that makes it one: a card face sits inside it."""
    faces = cards_on(page)

    def is_card_border(r):
        return any(abs(r.x0 - f.x0) < 4 and abs(r.y0 - f.y0) < 4
                   and abs(r.x1 - f.x1) < 5 and abs(r.y1 - f.y1) < 5 for f in faces)
    out = []
    for d in page.get_drawings():
        if d['type'] != 'f':
            continue
        s, f = _sig(d), d.get('fill')
        if s == 'llll' and _near(f, CREAM, .08):
            out.append(d['rect'])
        elif s == 're' and f and max(f) < .25 and not is_card_border(d['rect']):
            out.append(d['rect'])
    return out


def strip_callouts(page):
    """Remove the arrows and the number diamonds from a page, leaving everything
    else exactly as printed. Call it AFTER build() — it removes the very art
    build() reads. Returns (arrows, diamonds) dropped."""
    page.clean_contents()                      # one stream to edit, not several
    xrefs = page.get_contents()
    if len(xrefs) != 1:
        return 0, 0
    H = page.rect.y1
    tips = []
    for d in page.get_drawings():
        if (d['type'] == 's' and (d.get('width') or 0) > 3 and _near(d.get('color'), TEAL)) \
                or (d['type'] == 'f' and _near(d.get('fill'), TEAL) and _sig(d) == 'lll'):
            p = d['items'][0][1]
            tips.append((p.x, p.y))
    decor = _decor_rects(page)
    src = page.read_contents()
    arrows = [0]

    def sub(m):
        x, y = float(m.group(1)), H - float(m.group(2))
        if any(abs(x - tx) < .6 and abs(y - ty) < .6 for tx, ty in tips):
            arrows[0] += 1
            return b''
        return m.group(0)
    out = _BLOCK.sub(sub, src)
    # the diamonds are each their own Form XObject; drop the call that draws it,
    # which touches this page only (the XObject itself may be shared)
    dias = 0
    for xref, name, _t, bb in page.get_xobjects():
        dev = fitz.Rect(bb[0], H - bb[3], bb[2], H - bb[1])
        if not any(abs(dev.x0 - r.x0) < 1.5 and abs(dev.y0 - r.y0) < 1.5
                   and abs(dev.x1 - r.x1) < 1.5 and abs(dev.y1 - r.y1) < 1.5 for r in decor):
            continue
        out, n = _xobj_re(name.encode()).subn(b'', out)
        dias += n
    if arrows[0] or dias:
        page.parent.update_stream(xrefs[0], out)
    return arrows[0], dias


def diamonds_on(page):
    """The numbered diamonds. The number is set twice (fill over shadow), so the
    extracted string doubles: '13' comes out '1313'."""
    out = []
    for b in page.get_text('dict')['blocks']:
        if b['type']:
            continue
        for l in b['lines']:
            s = l['spans'][0]
            if s['size'] <= 25 or not pg.is_head_font(s['font']):
                continue
            t = ''.join(x['text'] for x in l['spans']).strip()
            if len(t) % 2 == 0 and t[:len(t) // 2] == t[len(t) // 2:]:
                t = t[:len(t) // 2]
            if t.isdigit():
                r = fitz.Rect(l['bbox'])
                out.append({'n': int(t), 'c': ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)})
    return out


def titles_on(page):
    """The card names, set as headings. A name may wrap ('Carta pequeña' /
    'de Investigador'), so adjacent heading lines that stack up are rejoined."""
    lines = []
    for b in page.get_text('dict')['blocks']:
        if b['type']:
            continue
        for l in b['lines']:
            s = l['spans'][0]
            t = ''.join(x['text'] for x in l['spans']).strip()
            if not t or not pg.is_head_font(s['font']) or not (17 <= s['size'] < 22):
                continue
            if ROMAN.match(t):
                continue
            lines.append({'t': t, 'r': fitz.Rect(l['bbox'])})
    lines.sort(key=lambda x: (round(x['r'].y0), x['r'].x0))
    out = []
    for ln in lines:
        prev = out[-1] if out else None
        # A wrapped name's lines sit a line apart and overlap horizontally. Display
        # faces are set tight, so the next line can start a hair ABOVE the previous
        # one's descender — hence the small negative tolerance. Two names side by
        # side share a baseline, which that tolerance still rejects.
        gap = ln['r'].y0 - prev['r'].y1 if prev else 0
        if prev and -ln['r'].height * .35 < gap < ln['r'].height * .9 \
                and min(prev['r'].x1, ln['r'].x1) - max(prev['r'].x0, ln['r'].x0) > 0:
            prev['t'] += ' ' + ln['t']
            prev['r'] |= ln['r']
        else:
            out.append(dict(ln))
    return out


def panels_on(page):
    """The key's backing panel: a big plain rect, pale but not white."""
    out = []
    for d in page.get_drawings():
        if d['type'] != 'f' or _sig(d) != 're':
            continue
        f = d.get('fill')
        if not f or len(f) != 3:
            continue
        if 0.80 < min(f) and max(f) < 0.96 and d['rect'].get_area() > 40000:
            out.append(d['rect'])
    return out


def _join_spans(groups, callout_red):
    """Span-runs of one item's lines -> runs, de-hyphenating each line break the
    same way the body parser does."""
    runs = []
    for i, spans in enumerate(groups):
        nxt = pg.build_runs(spans, callout_red)
        if not nxt:
            continue
        if not runs:
            runs = nxt
            continue
        tight = False
        if runs[-1]['kind'] == 'text':
            t = runs[-1]['t'].rstrip()
            if re.search(r'[^\W\d_]-$', t, re.UNICODE):
                runs[-1]['t'] = t[:-1]
                tight = True
        if not tight:
            if runs[-1]['kind'] == 'text' and not runs[-1]['t'].endswith(' '):
                runs[-1]['t'] += ' '
            elif runs[-1]['kind'] != 'text' and nxt[0]['kind'] == 'text' \
                    and not nxt[0]['t'].startswith(' '):
                nxt[0]['t'] = ' ' + nxt[0]['t']
        runs.extend(nxt)
    return pg.merge_runs(runs)


def _split_term(runs):
    """The book bolds a key item's term and ends it with a colon. The bolding is
    unreliable (a run can straddle the colon); the colon is not. So the colon
    splits it — which is also what the book means."""
    term, desc, cut = [], [], False
    for r in runs:
        if cut or r['kind'] != 'text' or ':' not in r['t']:
            (desc if cut else term).append(dict(r))
            continue
        head, _, tail = r['t'].partition(':')
        if head:
            term.append(dict(r, t=head))
        if tail.strip():
            desc.append(dict(r, t=tail.lstrip(), bold=False))
        cut = True
    if not cut:                    # no colon: it is all description
        return [], pg.merge_runs(term)
    for r in term:
        r['bold'] = False          # the term is emphasised by the markup, not the run
    return pg.merge_runs(term), pg.merge_runs(desc)


def key_on(page, panel, callout_red=None):
    """(title, [{n, term, desc}]) for one key panel. The items are numbered, so
    the numbers put them in order and the two-column layout costs nothing."""
    head, items, cur = [], [], None
    for b in page.get_text('dict', clip=panel, sort=False)['blocks']:
        if b['type']:
            continue
        for l in b['lines']:
            spans = [s for s in l['spans'] if s['text'] != '']
            if not spans or not ''.join(s['text'] for s in spans).strip():
                continue
            s0 = spans[0]
            if pg.is_head_font(s0['font']) and s0['size'] > 12:
                head.append(pg.norm(''.join(s['text'] for s in spans)))
                continue
            txt = ''.join(s['text'] for s in spans).strip()
            m = LEAD.match(txt)
            if m:
                # drop the "N." lead from the first span's text only
                spans = [dict(s) for s in spans]
                for s in spans:
                    if s['text'].strip():
                        s['text'] = LEAD.sub('', s['text'].lstrip(), count=1)
                        break
                cur = {'n': int(m.group(1)), 'groups': [spans]}
                items.append(cur)
            elif cur is not None:
                cur['groups'].append(spans)
    out = []
    for it in sorted(items, key=lambda i: i['n']):
        term, desc = _split_term(_join_spans(it['groups'], callout_red))
        out.append({'n': it['n'], 'term': term, 'desc': desc})
    return pg.norm(' '.join(head)), out


def _title_for(card, titles):
    """A card's name is the heading above it, nearest in both axes."""
    above = [t for t in titles if t['r'].y1 <= card.y0 + 4]
    if not above:
        above = titles
    if not above:
        return None
    cx = (card.x0 + card.x1) / 2
    return min(above, key=lambda t: abs((t['r'].x0 + t['r'].x1) / 2 - cx) + (card.y0 - t['r'].y1) * 1.5)


def build(pack, pages, doc=None, verbose=True):
    """Read the anatomy chapter out of `pages` (1-indexed) of the pack's newest PDF.

    Returns [{id, title, items:[...], cards:[{id, title, clip, page, markers}]}] —
    one entry per key. A card belongs to the last key seen at or before its page,
    which is how the book reads: a key heads the cards it explains.
    """
    close = doc is None
    if doc is None:
        doc = fitz.open(pack.require_pdf())
    # This module opens (or is handed) its own document, so it must tell the run
    # builder which red THIS edition calls out with. Relying on whatever parse_pdf
    # last set would make the answer depend on call order across modules — and on
    # `python tools/render_images.py <code>` alone, parse_pdf never runs at all.
    callout_red = pg.callout_red_of_doc(doc)
    keys, orphans, seen = [], 0, {}
    for pno in sorted(pages):
        if pno > doc.page_count:
            raise pg.langpack.PackError(
                f'langs/{pack.code}/lang.json: card anatomy names page {pno}, but '
                f'{pack.current["pdf"]} only has {doc.page_count} pages.')
        page = doc[pno - 1]
        for panel in panels_on(page):
            title, items = key_on(page, panel, callout_red)
            if items:
                keys.append({'id': pg.slugify(title), 'title': title, 'items': items, 'cards': []})
        if not keys:
            continue
        cards, arrows, dias, titles = cards_on(page), arrows_on(page), diamonds_on(page), titles_on(page)
        for c in sorted(cards, key=lambda r: (round(r.y0), r.x0)):
            hot = c + (-4, -4, 4, 4)
            clip = c + (-2.5, -2.5, 2.5, 2.5)      # take the card's printed border with it
            markers = []
            for a in arrows:
                if fitz.Point(*a['apex']) not in hot:
                    continue
                d = min(dias, key=lambda b: math.dist(b['c'], a['tail'])) if dias else None
                if d is None or math.dist(d['c'], a['tail']) > 40:
                    orphans += 1
                    continue
                markers.append({'n': d['n'],
                                'x': round((a['apex'][0] - clip.x0) / clip.width * 100, 2),
                                'y': round((a['apex'][1] - clip.y0) / clip.height * 100, 2)})
            t = _title_for(c, titles)
            name = t['t'] if t else 'card'
            slug = pg.slugify(name)
            seen[slug] = seen.get(slug, 0) + 1
            if seen[slug] > 1:
                slug = '%s-%d' % (slug, seen[slug])
            keys[-1]['cards'].append({
                'id': slug, 'title': name, 'page': pno,
                'clip': [round(v, 2) for v in (clip.x0, clip.y0, clip.x1, clip.y1)],
                'markers': sorted(markers, key=lambda m: m['n']),
            })
    if close:
        doc.close()
    ncards = sum(len(k['cards']) for k in keys)
    if verbose:
        print('  card anatomy: %d key(s), %d card(s), %d marker(s)'
              % (len(keys), ncards, sum(len(c['markers']) for k in keys for c in k['cards'])))
    if not keys or not ncards:
        print('  WARNING: card anatomy found nothing on pages %s of %s — the section '
              'will fall back to page images.' % (sorted(pages), pack.current['pdf']))
        return []
    if orphans:
        print('  WARNING: %d card-anatomy arrow(s) had no number beside them; they '
              'were dropped.' % orphans)
    # every number the key explains should be pointed at by some card
    for k in keys:
        used = {m['n'] for c in k['cards'] for m in c['markers']}
        miss = sorted({i['n'] for i in k['items']} - used)
        if miss:
            print('  note: key %r explains %s, which no arrow points at.' % (k['title'], miss))
    return keys
