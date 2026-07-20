# -*- coding: utf-8 -*-
"""Rebuild the product-icon reference chapter from the page's own vector art.

The book prints this chapter as a list: a group heading, a paragraph, then one small
icon per product with its name beside it. Flattened to a JPG it is unreadable, uncopyable
and unsearchable — and the QR beside it is a dead picture of a link.

Everything here is found by SHAPE, COLOUR and GEOMETRY, never by wording:

  the chapter   the pack already names it (num/title); its heading span gives the x of
                the column it occupies, and everything is read from that column only.
                Necessary, not fussy: the English edition prints chapters XIII, XIV and
                XV on ONE spread, so "the page" is three chapters.
  an icon       a small dark filled path (7-16pt square) with no text to its left
  its name      the text line whose left edge meets the icon's right edge
  a group       the last heading above the icon in the same column
  the QR        fifty-plus tiny dark squares whose union is square

The art is identical in every language (the paths agree to 0.01 units in a 0..100
viewBox), so one pack renders the SVGs for everybody — the same rule the game icons
already follow (langpack.icon_art_pack). Only the names are translated.
"""
import re

import parse_grimoire as pg
import langpack


def _dark(f):
    """The book's ink. A range, not an exact colour: the Spanish edition prints
    (0.137,0.122,0.125) and the English (0,0,0), so matching either one exactly finds
    every icon in one language and none in the other."""
    return bool(f) and len(f) == 3 and max(f) < .25


def _filled(d):
    """A path the book fills with its ink.

    NOT type == 'f'. PyMuPDF reports a path the book both fills AND strokes as 'fs', and
    demanding fill-only drops it silently. One mark in thirty on the substitution page is
    drawn that way in BOTH editions ("Frío helador" / "Chilling Cold", 6 paths, all 'fs')
    and came back as an empty square; "Gules" mixes 11 'f' with 2 'fs' and had been
    rendering with two of its paths missing, which nobody could see was wrong.

    Shared with fingerprint() on purpose: a name counts the paths, so if the two ever
    disagreed about what a path is, two different marks could answer to one name."""
    return 'f' in d['type'] and _dark(d.get('fill'))


def _pale(f):
    """Paper, or the ink's opposite — what a knocked-out mark is drawn in."""
    return bool(f) and len(f) == 3 and min(f) > .75


def _knocked_out(drawings):
    """The white paths of a mark printed in reverse, or [] if it is printed normally.

    Some products' marks are not drawn in ink on paper: they are drawn in PAPER on a plate
    of ink — a shape cut out of a filled square. Tracing "the dark filled paths" then yields
    the plate and throws the mark away, which is how the German edition's "Rückkehr zu…"
    products came out as blank squares. (The English edition does this to exactly one mark,
    Return to the Night of the Zealot, which is why that one alone needed a hand-written
    answer.)

    A plate is recognisable without knowing anything about the artwork: it is dark, it is
    almost featureless (a rectangle or a rounded rectangle — a couple of items), and the
    pale paths sit inside it and carry the detail. Requiring the pale paths to be the more
    detailed of the two keeps a mark that merely sits on a tinted background from inverting."""
    plates = [d for d in drawings if 'f' in d['type'] and _dark(d.get('fill'))
              and len(d['items']) <= 2]
    if not plates:
        return None, []
    plate = max(plates, key=lambda d: d['rect'].get_area())
    inside = [d for d in drawings
              if 'f' in d['type'] and _pale(d.get('fill')) and d is not plate
              and d['rect'].x0 >= plate['rect'].x0 - 1 and d['rect'].x1 <= plate['rect'].x1 + 1
              and d['rect'].y0 >= plate['rect'].y0 - 1 and d['rect'].y1 <= plate['rect'].y1 + 1]
    if not inside:
        return None, []
    if sum(len(d['items']) for d in inside) <= sum(len(d['items']) for d in plates):
        return None, []
    return plate, inside


def _rect(d):
    r = d['rect']
    return (r.x0, r.y0, r.x1, r.y1)


def _sig(d):
    return ''.join(i[0] for i in d['items'])


# ---- the chapter's column --------------------------------------------------
def _textblocks(page):
    """Text blocks only. An image block carries no 'lines', and column_edges reads
    them — the same contract parse_grimoire uses everywhere."""
    return [b for b in page.get_text('dict')['blocks'] if b['type'] == 0]


def _heads(page):
    """Every heading on the page, as (x, y, size, text). Size is returned rather than
    filtered here because the page carries two ranks of heading and they are told apart
    by nothing but their size: the chapter's own title is ~18.9pt and a group's is
    ~14.7pt. Both are the heading face."""
    out = []
    for b in _textblocks(page):
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['text'].strip() and pg.is_head_font(s['font']):
                    out.append((s['bbox'][0], s['bbox'][1], s['size'], s['text'].strip()))
    return out


CHAPTER_SZ = 15.5      # at or above: the chapter's own title
GROUP_SZ = (13.5, 15.5)   # between: a group heading inside it


def box_of_chapter(page, sec):
    """-> (x_lo, y_lo, x_hi, y_hi): the region of the page this chapter owns, or None.

    A column, bounded below by whatever chapter starts under it. Both bounds are needed
    and neither is paranoia: the English edition sets chapters XIII, XIV and XV on one
    1224pt spread in four columns, so "the page" is three chapters and "the column"
    could still be two.

    The pack says what the chapter is called and what numeral it carries; that is the
    same evidence assemble.match_section already trusts, and it is the only thing on the
    page that can tell chapter XIV from chapters XIII and XV beside it."""
    want_num = (sec.get('num') or '').strip()
    want_title = pg.norm(sec['title'])
    chapters = [(x, y, sz, t) for x, y, sz, t in _heads(page) if sz >= CHAPTER_SZ]
    for x0, y0, sz, text in chapters:
        n = pg.norm(text)
        m = re.match(r'^\s*([IVXLC]+)\.\s*(.*)$', text)
        hit = (m and want_num and m.group(1) == want_num) or \
              (want_title and (n.startswith(want_title) or want_title in n))
        if not hit:
            continue
        # Bounded on the right by whatever chapter starts to the right of mine, and NOT
        # by parse_grimoire.column_edges: that finds columns of TEXT, and this chapter is
        # a full-width grid whose caption sub-columns look exactly like text columns —
        # it comes out 185pt wide instead of 576. A chapter's own title is the only thing
        # that marks where the next chapter begins.
        right = [hx for hx, hy, hsz, _t in chapters if hx > x0 + 20]
        col = (x0 - 8, (min(right) if right else page.rect.x1) - 8)
        # Bounded below by the next CHAPTER heading sharing this column — but not by the
        # rest of my own title. "XV. Referencia de iconos de / conjuntos de encuentros"
        # is one heading set on two lines, and each line is its own 18.9pt span, so a
        # naive "next chapter" bound is the second line of this one and the chapter comes
        # out 18pt tall. A heading within a couple of line-heights, indented no further
        # than mine, is my own wrap.
        wrap = y0 + 2.2 * sz
        below = [hy for hx, hy, hsz, _t in _heads(page)
                 if hsz >= CHAPTER_SZ and hy > y0 + 1 and col[0] <= hx <= col[1]
                 and not (hy < wrap and hx <= x0 + 2)]
        # The page number and the running head sit below every text frame in the book,
        # and they are inside this box like anything else — so the chapter stops where
        # parse_grimoire already says the page's content stops, or the running head lands
        # in the chapter's prose ("45 ARKHAM GRIMOIRE ...").
        bottom = min(below) if below else min(page.rect.y1, pg.FOOT_Y)
        return (col[0], y0, col[1], bottom)
    return None


# ---- the QR ----------------------------------------------------------------
def qr_on(page, box):
    """-> the QR's rect, or None. A QR is a crowd of tiny dark squares whose union is
    square. Nothing else on the page looks like that."""
    mods = [d for d in page.get_drawings()
            if d['type'] == 'f' and _sig(d) == 're' and _dark(d.get('fill'))
            and (d['rect'].x1 - d['rect'].x0) < 25
            and _in_box((d['rect'].x0, d['rect'].y0), box)]
    if len(mods) < 50:
        return None
    x0 = min(d['rect'].x0 for d in mods); y0 = min(d['rect'].y0 for d in mods)
    x1 = max(d['rect'].x1 for d in mods); y1 = max(d['rect'].y1 for d in mods)
    if abs((x1 - x0) - (y1 - y0)) > 1.5:
        return None
    return (x0, y0, x1, y1)


def _in_box(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def _inside(r, box, pad=1.0):
    return (r[0] >= box[0] - pad and r[1] >= box[1] - pad
            and r[2] <= box[2] + pad and r[3] <= box[3] + pad)


# ---- the icons -------------------------------------------------------------
def _lines(page, box):
    """Text lines inside the chapter's box, as (x0, y0, x1, y1, text)."""
    out = []
    for b in _textblocks(page):
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if not t:
                continue
            x0, y0, x1, y1 = l['bbox']
            if _in_box((x0, y0), box):
                out.append((x0, y0, x1, y1, t))
    return out


def icons_on(page, box, qr):
    """-> [(cell_rect, name)] — one per product icon, paired with its printed name.

    The "nothing to my left" test is what makes this safe. The same 10pt glyph appears
    inline in running prose elsewhere in the book ("Machete (<icon>20)"), identical in
    size and colour; only the absence of text ending at its left edge tells the list
    apart from the sentence."""
    cands = [d for d in page.get_drawings()
             if d['type'] == 'f' and _dark(d.get('fill'))
             and 7 < (d['rect'].x1 - d['rect'].x0) < 16
             and 7 < (d['rect'].y1 - d['rect'].y0) < 16
             and _in_box((d['rect'].x0, d['rect'].y0), box)
             and not (qr and _inside(_rect(d), qr, 2))]
    lines = _lines(page, box)
    out = []
    seen = []
    for d in cands:
        r = _rect(d)
        if any(_inside(r, s, .6) for s in seen):
            continue                       # already collected into a cell
        cy = (r[1] + r[3]) / 2
        # a label starts where the icon ends, on the icon's own row
        label = None
        for lx0, ly0, lx1, ly1, t in lines:
            if abs(lx0 - r[2]) < 2.5 and ly0 - 2 <= cy <= ly1 + 2:
                label = t; break
        if not label:
            continue
        # ...and nothing may end at its left edge, or it is mid-sentence
        if any(abs(lx1 - r[0]) < 2.5 and ly0 - 2 <= cy <= ly1 + 2
               for lx0, ly0, lx1, ly1, t in lines):
            continue
        # the cell is every dark path inside the glyph's box: one icon can be more than
        # one path (a ring plus its centre dot), and dropping the dot changes the mark
        cell = [r]
        for e in cands:
            er = _rect(e)
            if er != r and _inside(er, r, .6):
                cell.append(er)
        box = (min(c[0] for c in cell), min(c[1] for c in cell),
               max(c[2] for c in cell), max(c[3] for c in cell))
        seen.append(box)
        out.append((box, label, [label]))
    out.sort(key=lambda it: (it[0][1], it[0][0]))
    return out


# ---- icons drawn as a grid of clusters -------------------------------------
# The two icon chapters are drawn differently, and the difference is real rather than
# incidental. Chapter XIV sets a 10pt mark hard against its name (gap < 2.5pt) and every
# mark is one path. Chapter XV sets a 20pt mark with its name ~15pt away, and a mark is
# a CROWD of paths — a badge, a silhouette, a few highlights — none of which contains the
# others, so "collect what is inside the first path" collects one third of a drawing.
# So they are clustered: paths that all but touch are one drawing. Measured, not guessed:
# within an icon the paths are <1pt apart, and the nearest two DIFFERENT icons on these
# pages are ~28pt apart, so anything in between is the same answer.
CLUSTER_GAP = 4.0


def _near(a, b, gap):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


def _clusters(rects, gap=CLUSTER_GAP):
    """Union-find over rects: everything that all but touches is one drawing."""
    parent = list(range(len(rects)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _near(rects[i], rects[j], gap):
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    out = {}
    for i, r in enumerate(rects):
        out.setdefault(find(i), []).append(r)
    return [(min(c[0] for c in g), min(c[1] for c in g),
             max(c[2] for c in g), max(c[3] for c in g)) for g in out.values()]


def grid_icons_on(page, box, minsize=14.0, maxgap=44.0):
    # minsize is the icon's LONG side, not both sides. Two of these marks are tall and
    # narrow (12.7pt and 13.9pt wide, both ~21.5pt tall) and testing both dimensions
    # silently dropped exactly those two — a chapter of 23 quietly shipping 21. The
    # detail paths inside a mark are at most 6pt on their long side and the marks are at
    # least 20pt, so the two populations do not come close to touching.
    """-> [(cluster_rect, caption)] for a chapter that lays its icons out as a grid.

    The caption is the nearest text line beginning to the right of the icon on its own
    row. "Nearest" is safe here only because the icon's own row is required AND the gap
    is capped: the page runs two icon+caption columns side by side, so without the cap
    a column-one icon would happily marry a column-two caption 165pt away."""
    rects = [_rect(d) for d in page.get_drawings()
             if d['type'] == 'f' and _dark(d.get('fill'))
             and _in_box((d['rect'].x0, d['rect'].y0), box)]
    cl = [c for c in _clusters(rects)
          if max(c[2] - c[0], c[3] - c[1]) >= minsize]
    lines = _lines(page, box)
    out = []
    for c in cl:
        cy = (c[1] + c[3]) / 2
        best = None
        for lx0, ly0, lx1, ly1, t in lines:
            if lx0 < c[2] - 1 or not (ly0 - 4 <= cy <= ly1 + 4):
                continue
            gap = lx0 - c[2]
            if gap > maxgap:
                continue
            if best is None or gap < best[0]:
                best = (gap, t, (lx0, ly0, lx1, ly1, t))
        if best:
            out.append((c, best[1], best[2]))
    # A name too long for its cell is set on two lines ("Miskatonic / University"), and
    # only the first sits on the icon's row. The rest is the line directly under it,
    # starting at the same x, with no icon of its own — so it belongs to the name above
    # rather than to the chapter's prose, where it would otherwise surface as a stray
    # word. English needs this and Spanish does not: the same name fits on one line there.
    claimed = {ln[4] for _, _, ln in out}
    joined = []
    for c, txt, ln in out:
        parts = [txt]
        eaten = [txt]
        cur = ln
        while True:
            # top-to-top, not the gap between the boxes: consecutive lines of the same
            # caption OVERLAP by half a point (their line boxes are taller than the
            # leading), so a "gap > 0" test never fires. One line-step is ~10.8pt here.
            nxt = [o for o in lines
                   if o[4] not in claimed and abs(o[0] - cur[0]) < 4
                   and 4 < o[1] - cur[1] < 16]
            if not nxt:
                break
            nxt = min(nxt, key=lambda o: o[1])
            parts.append(nxt[4]); eaten.append(nxt[4]); claimed.add(nxt[4]); cur = nxt
        joined.append((c, _join(parts), eaten))
    joined.sort(key=lambda it: (it[0][1], it[0][0]))
    return joined


# ---- the art ---------------------------------------------------------------
def _fmt(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def icon_svg(page, box, inner_only=False):
    """The icon, as an SVG path normalised into a 0..100 viewBox.

    Segments are chained: a fresh `M` per segment would cut every subpath into an open
    stroke, which renders as an outline instead of a filled mark."""
    w = box[2] - box[0]; h = box[3] - box[1]
    sc = 100.0 / max(w, h)
    ox = box[0] - (max(w, h) - w) / 2
    oy = box[1] - (max(w, h) - h) / 2

    def P(p):
        return _fmt((p.x - ox) * sc), _fmt((p.y - oy) * sc)

    def segs(d):
        parts = []
        cur = None
        for it in d['items']:
            op = it[0]
            if op == 'l':
                a, b = it[1], it[2]
                if cur is None or (abs(cur.x - a.x) > 1e-6 or abs(cur.y - a.y) > 1e-6):
                    parts.append('M%s %s' % P(a))
                parts.append('L%s %s' % P(b)); cur = b
            elif op == 'c':
                a, b, c, e = it[1], it[2], it[3], it[4]
                if cur is None or (abs(cur.x - a.x) > 1e-6 or abs(cur.y - a.y) > 1e-6):
                    parts.append('M%s %s' % P(a))
                parts.append('C%s %s %s %s %s %s' % (P(b) + P(c) + P(e))); cur = e
            elif op in ('re', 'qu'):
                pts = ([it[1].top_left, it[1].top_right, it[1].bottom_right, it[1].bottom_left]
                       if op == 're' else [it[1][i] for i in range(4)])
                parts.append('M%s %s' % P(pts[0]))
                for p in pts[1:]:
                    parts.append('L%s %s' % P(p))
                parts.append('Z'); cur = None
        return parts

    here = [d for d in page.get_drawings() if _inside(_rect(d), box, .6)]
    if inner_only:
        # The mark's identity rather than its printing: the shape cut out of the plate,
        # without the plate. Editions disagree about the plate — the German book sets its
        # "Rückkehr zu…" marks on a square where every other edition uses a disc — but they
        # all cut out the same shape, so this is what says which product it is.
        p, ins = _knocked_out(here)
        if p is None:
            return None
        parts = []
        for d in ins:
            parts.extend(segs(d))
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                '<path fill-rule="evenodd" d="%s"/></svg>' % ''.join(parts)) if parts else None
    # A mark printed in reverse: the plate and the shapes cut out of it are ONE path with
    # an even-odd rule, so the pale shapes become holes. Emitting the pale paths on their
    # own would draw the mark the right way up but lose the plate around it — which is a
    # different mark: "Return to X" is exactly "X" inside a filled disc.
    plate, knocked = _knocked_out(here)
    if plate is not None:
        parts = []
        for d in [plate] + knocked:
            parts.extend(segs(d))
        if parts:
            return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                    '<path fill-rule="evenodd" d="%s"/></svg>' % ''.join(parts))

    paths = []
    for d in here:
        if not _filled(d):
            continue
        parts = segs(d)
        if not parts:
            continue
        rule = 'evenodd' if d.get('even_odd') else 'nonzero'
        paths.append(f'<path fill-rule="{rule}" d="{"".join(parts)}"/>')
    if not paths:
        return None
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            + ''.join(paths) + '</svg>')


# ---- the chapter -----------------------------------------------------------
def build(page, sec, verbose=True):
    """-> {'groups': [...], 'qr': rect|None} for one icon-reference chapter, or None.

    A group with no items is kept, not dropped. The book ships those headings empty on
    purpose — the products do not exist yet at v1.0 — and a chapter that quietly omits
    them would be telling the reader the game has fewer kinds of product than it does.
    Saying "nothing here yet" is the honest render, and it is what the book does."""
    box = box_of_chapter(page, sec)
    if box is None:
        return None
    qr = qr_on(page, box)
    # Which of the two layouts this chapter uses decides itself: the row rule finds
    # nothing on a grid page and the grid rule finds nothing on a row page. No pack flag,
    # no page number, no wording — the drawing answers.
    items = icons_on(page, box, qr) or grid_icons_on(page, box)
    claimed = {ln for _, _, eaten in items for ln in eaten}
    # Headings, wraps rejoined. The book sets a heading over two lines when it is long
    # ("Iconos de conjuntos de encuentros / de Hermanos de las cenizas"), and each line is
    # its own span; left apart they become two headings, the second one owning every icon.
    raw = sorted((y, x, t) for x, y, sz, t in _heads(page)
                 if GROUP_SZ[0] < sz < GROUP_SZ[1] and _in_box((x, y), box))
    heads = []
    headlines = set()          # every LINE a heading is set on, joined or not
    for hy, hx, ht in raw:
        headlines.add(ht)
        if heads and hy - heads[-1][0] < 22 and not any(hy - 4 <= b[1] <= hy + 16 for b, _l, _e in items):
            heads[-1] = (heads[-1][0], min(heads[-1][1], hx), heads[-1][2] + ' ' + ht)
        else:
            heads.append((hy, hx, ht))
    # Two ranks, told apart by indent alone: a heading flush with the chapter's own left
    # margin names an expansion; an indented (centred) one names a grid inside it. That is
    # the book's own typography, and it needs no word.
    margin = box[0] + 8
    lines = _lines(page, box)
    groups = []
    for i, (hy, hx, htext) in enumerate(heads):
        nexty = heads[i + 1][0] if i + 1 < len(heads) else box[3]
        level = 1 if abs(hx - margin) < 3 else 2
        # the blurb is what is left over: every line under this heading that is not
        # another icon's name. By identity, never by a y-cutoff — one label's line
        # starts 0.16pt ABOVE its own icon, so a cutoff swallows it into the prose.
        # Excluding every line the heading is SET ON, not just the joined title: a
        # heading broken over two lines would otherwise donate its second line to its
        # own description ("Iconos de conjuntos de encuentros" / "de Hermanos de las
        # cenizas").
        blurb = [t for lx0, ly0, lx1, ly1, t in lines
                 if hy < ly0 < nexty and t not in claimed and t not in headlines]
        mine = [(b, lbl) for b, lbl, _e in items if hy < b[1] < nexty]
        groups.append({
            'title': htext,
            'level': level,
            'blurb': _join(blurb),
            'items': [dict(_split_code(lbl, page, b), _box=b) for b, lbl in mine],
        })
    if verbose:
        n = sum(len(g['items']) for g in groups)
        empty = sum(1 for g in groups if not g['items'])
        print(f'  icon reference: {len(groups)} group(s) ({empty} not filled in yet), '
              f'{n} icon(s)' + (', QR decoded to a link' if qr else ', no QR'))
    return {'groups': groups, 'qr': qr}


_HYPH = re.compile(r'(\w)-\s+(\w)')


def _join(lines):
    """The book breaks words across lines with a hyphen; joining naively keeps it."""
    t = ' '.join(lines)
    t = _HYPH.sub(r'\1\2', t)
    return re.sub(r'\s+', ' ', t).strip()


# The product code, as the book prints it beside every icon. Letters+digits, no word:
# "AHC100" reads the same in Spanish and English, which is exactly why it is the join.
_CODE = re.compile(r'^\s*([A-Z]{2,4}\s*\d{2,4})\s+(.*)$')


def fingerprint(page, box):
    """A name for a drawing that has no printed code: how many paths it is made of, and
    how big it is, to a tenth of a point. The art is the same object in every edition, so
    every pack derives the same name from its own PDF with nothing shared between them —
    which is the only way this stays a data-only pipeline.
    Verified rather than assumed: on these pages all 23 marks get distinct fingerprints,
    and all 23 agree across the two languages."""
    n = sum(1 for d in page.get_drawings()
            if _filled(d) and _inside(_rect(d), box, .6))
    return 'e%d-%d-%d' % (n, round((box[2] - box[0]) * 10), round((box[3] - box[1]) * 10))


def _split_code(label, page=None, box=None):
    """-> {'code','name','art'}. The code is the one part of the label the book does NOT
    translate, so it is what joins each pack's own words to the one copy of the shared
    art. An encounter set is printed with no code at all — there, the drawing's own
    geometry is the name."""
    m = _CODE.match(label or '')
    if not m:
        art = fingerprint(page, box) if (page is not None and box) else None
        return {'code': None, 'name': (label or '').strip(), 'art': art}
    code = re.sub(r'\s+', '', m.group(1)).upper()
    return {'code': code, 'name': m.group(2).strip(), 'art': code}
