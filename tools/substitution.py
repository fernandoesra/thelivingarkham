# -*- coding: utf-8 -*-
"""Rebuild the core encounter set substitution table from the page's own vector art.

The book prints the table as three columns of marks — a legacy set, a connector, and
the set (or sets) that replace it — with every caption set to the RIGHT of the mark it
names. Read in reading order those captions are a jumble: "Agentes de Cthulhu /
Agentes de Hastur / ... / Putrefacción hedionda". So the table is recovered from the
geometry instead:

  * cluster the region's vector art and drop the QR, leaving only the table's marks;
  * band the clusters by x. The book draws three columns, so three bands come out. The
    middle band is the connector, and there is exactly one per row, which makes it the
    row's spine: every other mark joins the row whose connector it sits beside;
  * a caption belongs to the nearest mark on its left that shares its row and overlaps
    at least half the line. A connector can never win a caption that way — the icon it
    points at is always nearer — so the only text a connector CAN win is the operator
    the book prints inside it ("+", "o"/"or"), which is exactly where it belongs.

Two shapes of connector are drawn, and the difference is the whole point: a small arrow
means the row is one-for-one, a tall brace means the row fans out to several sets. The
geometry says which before a word is read.

Nothing here reads a word. es and en recover the same 14 rows, the same two fan-out
rows and the same operators from art that agrees to the decimal — which is the evidence
that the rule is the book's and not one edition's layout.

Not a text-block rule, deliberately: PyMuPDF's own block grouping crosses the columns
("Males cósmicos | Antiguos males" arrive as one block) and groups differently in each
language, so it reads clean in en and shreds es.
"""
import re
import parse_grimoire as pg
import icon_reference as ir

MIN_MARK = 10.0      # under this a cluster is a hairline or a stray, not a printed mark
BAND_GAP = 15.0      # x-centres nearer than this are the same printed column
HALF = 0.5           # a caption must sit at least half on the mark that owns it


def _is_qr(c, qr):
    """Is this cluster the QR code's own art?

    Not "does it sit inside the decoded square": the German and Italian editions print
    a white quiet-zone panel behind the code, so the drawn art is 5-9pt LARGER than the
    square the decoder reports, and a containment test left it standing as a fourth
    column of the table. What identifies it either way is that the two occupy the same
    place — so compare the overlap against the smaller of the two."""
    ix = max(0.0, min(c[2], qr[2]) - max(c[0], qr[0]))
    iy = max(0.0, min(c[3], qr[3]) - max(c[1], qr[1]))
    inter = ix * iy
    smaller = min((c[2] - c[0]) * (c[3] - c[1]), (qr[2] - qr[0]) * (qr[3] - qr[1]))
    return smaller > 0 and inter / smaller >= 0.8


def _marks(page, box):
    """Every printed mark in the region, minus the QR -> ([(x0,y0,x1,y1)], qr)."""
    qr = ir.qr_on(page, box)
    rects = []
    for d in page.get_drawings():
        r = d['rect']
        if (r.x0 >= box[0] and r.x1 <= box[2] and r.y0 >= box[1] and r.y1 <= box[3]
                and r.width > 0.4 and r.height > 0.4):
            rects.append((r.x0, r.y0, r.x1, r.y1))
    out = [c for c in ir._clusters(rects) if max(c[2] - c[0], c[3] - c[1]) >= MIN_MARK]
    if qr:
        out = [c for c in out if not _is_qr(c, qr)]
    return out, qr


def _bands(marks):
    """The printed columns, left to right -> [[mark]]."""
    out = []
    for m in sorted(marks, key=lambda m: (m[0] + m[2]) / 2):
        c = (m[0] + m[2]) / 2
        if out and c - (out[-1][-1][0] + out[-1][-1][2]) / 2 <= BAND_GAP:
            out[-1].append(m)
        else:
            out.append([m])
    return out


def _lines(page, box):
    """The region's body lines and its headings, kept apart by the face the book set
    them in — the same evidence parse_grimoire trusts. -> ([(bbox, text)], [(bbox, text)])"""
    body, heads = [], []
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        for l in b['lines']:
            t = ''.join(s['text'] for s in l['spans']).strip()
            x0, y0, x1, y1 = l['bbox']
            if not t or not (x0 >= box[0] and x1 <= box[2] and y0 >= box[1] and y1 <= box[3]):
                continue
            spans = [s for s in l['spans'] if s['text'].strip()]
            if any(pg.is_head_font(s['font']) for s in spans):
                heads.append((l['bbox'], t))
            else:
                body.append((l['bbox'], t))
    return body, heads


def _overlaps(line, mark):
    """How much of the line's height sits on the mark, 0..1."""
    lo, hi = max(line[1], mark[1]), min(line[3], mark[3])
    h = line[3] - line[1]
    return max(0.0, hi - lo) / h if h > 0 else 0.0


def build(page, sec, clip=None, verbose=True):
    """-> {'heading', 'rows': [{'from', 'op', 'to'}], 'qr'} or None if the page holds
    no such table. The pack's own figure clip picks the region: an edition that prints
    two book pages on one PDF page says so there, and nowhere else."""
    box = tuple(clip) if clip else tuple(page.rect)
    box = (box[0], box[1], box[2], min(box[3], pg.FOOT_Y))   # the folio and the running
    marks, qr = _marks(page, box)                            # foot are furniture, not table
    bands = _bands(marks)
    if len(bands) != 3:
        if verbose:
            print(f'  [subst] {sec["key"]}: {len(bands)} column(s) of art, not 3 — not a table')
        return None
    left, mid, right = bands
    if len(mid) != len(left):
        if verbose:
            print(f'  [subst] {sec["key"]}: {len(mid)} connector(s) for {len(left)} row(s)')
        return None

    # The connectors are the spine: one per row, so every other mark joins the row whose
    # connector it sits beside. Nothing here needs to know which way the arrow points —
    # the row is rendered in the order the book prints it.
    spine = sorted(((m[1] + m[3]) / 2, m) for m in mid)

    def row_of(m):
        cy = (m[1] + m[3]) / 2
        return min(range(len(spine)), key=lambda i: abs(spine[i][0] - cy))

    rows = [{'from': None, 'conn': spine[i][1], 'to': [], 'op': None} for i in range(len(spine))]
    for m in left:
        r = rows[row_of(m)]
        if r['from'] is not None:
            if verbose:
                print(f'  [subst] {sec["key"]}: two source marks on one row')
            return None
        r['from'] = m
    for m in right:
        rows[row_of(m)]['to'].append(m)
    if any(r['from'] is None or not r['to'] for r in rows):
        if verbose:
            print(f'  [subst] {sec["key"]}: a row came out with no source or no target')
        return None
    for r in rows:
        r['to'].sort(key=lambda m: m[1])

    # Each caption to the nearest mark on its left that shares its row and carries at
    # least half of it. The connector only ever wins the operator.
    caps = {}
    body, heads = _lines(page, box)
    # The table is not the page: it is the column its art is drawn in. Bounding the text
    # by the marks themselves keeps the facing column's prose out without the pack ever
    # naming a coordinate — and anything unexpected inside the column still fails loudly
    # below rather than arriving as a caption.
    edge = min(m[0] for m in marks) - 2
    body = [(bb, t) for bb, t in body if bb[0] >= edge]
    for bb, t in body:
        r = rows[row_of(bb)]
        near, best = None, -1.0
        for m in [r['from'], r['conn']] + r['to']:
            if m[2] > bb[0] + 1 or _overlaps(bb, m) < HALF:
                continue
            if m[2] > best:
                near, best = m, m[2]
        if near is None:
            # a caption's last line can hang below the mark it names ("medianoche" sits
            # 2.5pt onto a 24.7pt icon); the row and the column still place it
            for m in [r['from'], r['conn']] + r['to']:
                if m[2] <= bb[0] + 1 and m[2] > best:
                    near, best = m, m[2]
        if near is None:
            if verbose:
                print(f'  [subst] {sec["key"]}: nothing owns the caption {t!r}')
            return None
        caps.setdefault(near, []).append((bb[1], t))

    def label(m):
        """A caption's lines, rejoined.

        Deliberately NOT parse_grimoire's rule, which drops the hyphen a line break
        ends on: that is right for prose, where the typesetter inserted it to break
        "sustitucio-|nes", and wrong here. A caption is a set's name, and the book
        breaks names at a space — every wrapped caption in es and en does — except
        when the name already carries a hyphen and the break lands on it. Dropping it
        would print "ShubNiggurath". A language that hyphenated a caption would show
        it as a visible "sustitucio-nes" rather than fail quietly."""
        out = ''
        for _, t in sorted(caps.get(m, [])):
            out = t if not out else (out + t if out.endswith('-') else out + ' ' + t)
        return out

    out = []
    for r in rows:
        op = label(r['conn']).strip() or None
        cell = {'from': {'label': label(r['from']), '_box': r['from']},
                'op': op,
                'to': [{'label': label(m), '_box': m} for m in r['to']]}
        if not cell['from']['label'] or any(not t['label'] for t in cell['to']):
            if verbose:
                print(f'  [subst] {sec["key"]}: a mark came out with no caption')
            return None
        out.append(cell)

    # The heading the table is printed under — returned, not matched by wording, so
    # assemble.py can retire the entry whose body is this jumble.
    inside = [(bb[1], t) for bb, t in heads if bb[0] >= min(m[0] for m in left) - 12]
    heading = min(inside)[1] if inside else None

    # Which entry the QR belongs under: the last heading standing above it in the QR's
    # own column. The book runs a sentence that ends in a colon and then prints the code,
    # so the link is part of that entry and nowhere else — and asking the page rather
    # than the pack means an edition that moves it is followed, not corrected.
    qr_under = None
    if qr:
        above = [(bb[1], t) for bb, t in heads
                 if bb[1] < qr[1] and abs(bb[0] - qr[0]) < 300 and bb[0] < min(m[0] for m in left) - 12]
        if above:
            qr_under = max(above)[1]
    fan = sum(1 for c in out if len(c['to']) > 1)
    if verbose:
        print(f'  [subst] {sec["key"]}: {len(out)} row(s), {fan} fanning out, '
              f'qr={("under " + repr(qr_under)) if qr_under else ("yes, but under no heading" if qr else "no")}')
    return {'heading': heading, 'rows': out, 'qr': qr, 'qrUnder': qr_under}


def fingerprint(page, box):
    """A name for the art itself. Two rows can print the same mark — the two Midnight
    Masks rows do — so this names the DRAWING, never the row."""
    return 's' + ir.fingerprint(page, box)[1:]


_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def same_art(a, b, tol=0.05):
    """Whether two rebuilt marks are the same drawing.

    The book prints one mark on two rows — the Midnight Masks locations and its
    treacheries — and those are the same art sitting at different heights on the page.
    They do not come back byte-identical: each is normalised into its own 0..100 box,
    so the rounding lands a hundredth apart ("54.7" against "54.71"). Sameness is
    therefore compared at the precision the drawing is rendered at, not as text —
    a real difference between two marks is orders of magnitude larger than this."""
    if _NUM.sub('', a) != _NUM.sub('', b):
        return False
    na = [float(x) for x in _NUM.findall(a)]
    nb = [float(x) for x in _NUM.findall(b)]
    return len(na) == len(nb) and all(abs(x - y) <= tol for x, y in zip(na, nb))
