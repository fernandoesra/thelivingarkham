# -*- coding: utf-8 -*-
"""The set / campaign / scenario icons the FAQ prints before each card reference.

A card reference in the FAQ is "Name ( <icon> number)": the icon says which product the
card comes from. Unlike the game icons (which are font glyphs, handled by icons.py), these
are **vector art** drawn into the text — invisible to the text parser. So they are
recovered here, straight from the page:

  * on every page, find each "( … number)" whose parenthesis and number are separated by a
    gap that a dark filled path sits in — that gap is the icon;
  * trace the icon's paths, tight-boxed, into a 0..100 viewBox SVG (icon_reference.icon_svg,
    the same tracer the product-icon chapter uses), so it is a crisp, recolourable mask;
  * fingerprint the normalised shape so the ~500 references collapse onto the few dozen
    distinct products, one shared SVG each (assets/faqsets/<fp>.svg).

The result is a map keyed by (folded card name, printed number) -> fingerprint, which
`faq.py` uses to slot the icon back into the parsed "Name ( number)" run. The art is the
same in every language, so one build writes the SVGs for everybody; only which card sits
where changes, and that is read per language from that language's own PDF.
"""
import hashlib
import os
import re
import sys

import fitz

import icon_reference as ir
import parse_grimoire as pg
import cardlinks
import langpack

# The card name sitting just before the "(" — matched the same way cardlinks names the
# ArkhamDB link, so the two agree on the key. Anchored to the end of the pre-"(" text.
_TRAILING_NAME = re.compile(r'(' + cardlinks._NAME + r')\s*$')

FAQSETS_DIR = os.path.join(langpack.ROOT, 'assets', 'faqsets')
_NUM = re.compile(r'^\s*(\d+[a-z]?)')


def _fold_name(s):
    return langpack.fold(re.sub(r'\s+', ' ', s or '').strip())


def _fingerprint(svg):
    """Scale-invariant id for a normalised (0..100) icon: round every coordinate to an
    8-unit grid and hash. The same shape at any size lands on the same id (with tolerance
    for tracing noise), so the hundreds of inline marks collapse onto the few dozen real
    products."""
    if not svg:
        return None
    body = svg.split('viewBox="0 0 100 100">', 1)[-1]
    q = [str(int(round(float(n) / 8.0))) for n in re.findall(r'-?\d+\.?\d*', body)]
    return 'e%d-%s' % (svg.count('<path'), hashlib.md5(','.join(q).encode()).hexdigest()[:8])


def _tight_box(page, gx0, gx1, gy0, gy1):
    """Union bbox of the dark filled paths whose centre falls in the gap between the
    parenthesis and the number. Tight, so the same icon always traces the same paths."""
    xs = []
    for d in page.get_drawings():
        if not ir._filled(d):
            continue
        r = d['rect']
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if gx0 - 1 <= cx <= gx1 + 1 and gy0 - 2 <= cy <= gy1 + 2:
            xs.append((r.x0, r.y0, r.x1, r.y1))
    if not xs:
        return None
    return (min(b[0] for b in xs), min(b[1] for b in xs),
            max(b[2] for b in xs), max(b[3] for b in xs))


def _cluster_icons(page):
    """Every set/campaign/scenario icon on the page, as (box, svg, fingerprint).

    The icons are dark vector art (the game icons are font glyphs, handled elsewhere), so
    the filled dark paths are clustered by proximity — each cluster is one icon — and traced.
    This finds ALL of them, wherever they sit in the text, not only before a card number."""
    rects = []
    for d in page.get_drawings():
        if not ir._filled(d):
            continue
        r = d['rect']
        if r.width <= 0 or r.height <= 0 or r.width > 40 or r.height > 40:
            continue
        rects.append([r.x0, r.y0, r.x1, r.y1])
    n = len(rects)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    gap = 3.0
    for i in range(n):
        a = rects[i]
        for j in range(i + 1, n):
            b = rects[j]
            if not (a[0] > b[2] + gap or b[0] > a[2] + gap or a[1] > b[3] + gap or b[1] > a[3] + gap):
                pi, pj = find(i), find(j)
                if pi != pj:
                    parent[pi] = pj
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(rects[i])
    out = []
    for g in clusters.values():
        box = (min(r[0] for r in g), min(r[1] for r in g),
               max(r[2] for r in g), max(r[3] for r in g))
        w, h = box[2] - box[0], box[3] - box[1]
        if not (3 <= w <= 22 and 3 <= h <= 22):
            continue                       # too small (a stray mark) or too big (not an icon)
        svg = ir.icon_svg(page, box)
        fp = _fingerprint(svg)
        if fp and svg:
            out.append((box, svg, fp))
    return out


_SETICON_FONT = 'TLA-SETICON'


def _place_icon(plines, box, fp):
    """Slot one icon into the text as a `seticon` span, INSIDE the line it interrupts, at its own
    x. A card reference "Name ( <icon> 20)" prints a dedicated space span where the vector icon is
    drawn (between the "(" span and the number span), so the icon goes at that x. Placing it as a
    span (not a separate pseudo-line, as it was before) is what stops stray "[icon]" paragraphs and
    split words ("espe <icon> cial") when the whole reference sits inside one line."""
    icx, icy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    span = {'font': _SETICON_FONT, 'text': '', '_fp': fp,
            'bbox': (box[0], box[1], box[2], box[3]), 'size': 10.0, 'color': 0}
    row = [l for l in plines if l['y'] - 3 <= icy <= l['y1'] + 3]     # lines on the icon's row
    if not row:
        if not plines:
            return
        row = [min(plines, key=lambda l: abs((l['y'] + l['y1']) / 2.0 - icy))]
    # 1) the icon sits within a line's x-range (the usual "( <icon> 20)" on one line): insert the
    #    seticon span before the first span starting to its right, so it lands between "(" and "20".
    for l in row:
        xs = [s['bbox'][0] for s in l['spans']]
        xe = [s['bbox'][2] for s in l['spans']]
        if min(xs) - 2 <= icx <= max(xe) + 2:
            idx = len(l['spans'])
            for i, s in enumerate(l['spans']):
                if s['bbox'][0] >= icx:
                    idx = i
                    break
            l['spans'].insert(idx, span)
            return
    # 2) the reference is split across two lines ("Name (" then "20) ..." a couple of points apart
    #    in y): append to the same-row line ending just left of the icon, so the row sort keeps it
    #    in order.
    left = [l for l in row if max(s['bbox'][2] for s in l['spans']) <= icx + 3]
    host = max(left, key=lambda l: max(s['bbox'][2] for s in l['spans'])) if left else row[0]
    host['spans'].append(span)


_NEAR = 26.0                           # how close the text on either side of an inline mark is


def _inline_gap(plines, box):
    """True when this mark sits in a GAP BETWEEN two pieces of text of the same column.

    That is how an inline mark is set — "(Nathaniel Cho <icon>, Harvey Walters <icon>…" — and it
    is never how the icon-reference tables set theirs: those sit at the left margin of their
    column, with nothing of that column to their left. The column matters. On the FAQ's last
    page the tables sit beside the environments prose, so a table's mark DOES have text a few
    points to its left — the prose ending in the column before it. Asking per column tells the
    two apart; asking of the whole row does not."""
    cy = (box[1] + box[3]) / 2.0
    row = [l for l in plines if l['y'] - 3 <= cy <= l['y1'] + 3]
    for col in {l.get('col') for l in row}:
        spans = [s for l in row if l.get('col') == col for s in l['spans']]
        left = any(box[0] - _NEAR <= s['bbox'][2] <= box[0] + 1 for s in spans)
        right = any(box[2] - 1 <= s['bbox'][0] <= box[2] + _NEAR for s in spans)
        if left and right:
            return True
    return False


def _inject_icons(lines, doc, inline_only_pages=()):
    """Slot every page's icons into the text as `seticon` spans (see _place_icon), then restore
    reading order. Returns {fingerprint: svg}.

    On a page in `inline_only_pages` only the marks set INSIDE the text are taken (see
    _inline_gap). That is the FAQ's last page, where the icon-reference tables share the paper
    with the environments prose: taking everything there dropped the tables' whole alphabet into
    the prose, and taking nothing — which is what the build did until now — left the five starter
    decks named in that prose with no marks at all."""
    by_page = {}
    for l in lines:
        by_page.setdefault(l['page'], []).append(l)
    svgs = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        plines = by_page.get(pno + 1, [])
        inline_only = (pno + 1) in inline_only_pages
        for box, svg, fp in _cluster_icons(page):
            if inline_only and not _inline_gap(plines, box):
                continue
            svgs.setdefault(fp, svg)
            _place_icon(plines, box, fp)
    # Reading order, per page and column, but CLUSTER lines into visual rows first and sort
    # left-to-right within a row. A card reference split by its inline icon leaves two spans on
    # the same visual line a couple of points apart in y ("Name (" at y419, "255) …" at y417);
    # sorting by rounded-y alone flips them ("255) …" before "Name ("). Grouping y within a few
    # points and then ordering by x keeps the sentence — and the icon — in order.
    lines.sort(key=lambda r: (r['page'], r['col'], r['y']))
    rowid, prev = 0, None
    for l in lines:
        key = (l['page'], l['col'])
        if prev is None or prev[0] != key or l['y'] - prev[1] > 4:
            rowid += 1
        l['_row'] = rowid
        prev = (key, l['y'])
    lines.sort(key=lambda r: (r['_row'], r['x0']))
    for l in lines:
        l.pop('_row', None)
    return svgs


def _drop_footers(lines, doc):
    """The running footer the FAQ prints on EVERY page — a small blackletter "PREGUNTAS
    FRECUENTES" / "FREQUENTLY ASKED QUESTIONS" and the page number beside it — leaks into the
    prose (it landed as a stray "12 PREGUNTAS FRECUENTES" paragraph inside entries, even inside
    a refraction). The Grimoire drops footers by an absolute y (FOOT_Y, tuned to its 792pt page);
    the FAQ page is only 684pt tall, so that cut misses it. Dropped here by signature instead —
    bottom band + a bare page number or a small heading-font span — page-height- and
    language-neutral, and confined to the FAQ (this is only reached from parse_with_icons)."""
    heights = {}

    def page_h(pno):
        if pno not in heights:
            heights[pno] = doc[pno - 1].rect.height
        return heights[pno]

    def is_footer(l):
        if l['y'] < page_h(l['page']) - 45:       # not in the bottom band
            return False
        spans = l['spans']
        txt = ''.join(s['text'] for s in spans).strip()
        if re.fullmatch(r'\d{1,4}', txt):         # a bare page number
            return True
        return any('Teutonic' in s.get('font', '') and s.get('size', 99) < 13
                   and s['text'].strip() for s in spans)   # the running blackletter footer

    return [l for l in lines if not is_footer(l)]


def parse_with_icons(pdf, inline_only_pages=()):
    """parse_grimoire.parse_pdf, but with the FAQ's vector set icons recovered and slotted
    back into the text. Returns (nodes, doc, svgs). Done by patching the two module hooks
    the parser resolves at call time — collect_lines (to inject the icons) and build_runs
    (to turn an injected icon span into a `seticon` run) — so the parser is reused wholesale."""
    orig_collect = pg.collect_lines
    orig_build = pg.build_runs
    captured = {}

    def collect(pdf_, masks):
        lines, doc = orig_collect(pdf_, masks)
        lines[:] = _drop_footers(lines, doc)
        captured['svgs'] = _inject_icons(lines, doc, inline_only_pages)
        return lines, doc

    def build(spans, reds=pg._KEEP):
        # A line now carries seticon spans mixed in with text (the icon sits between "(" and the
        # number of a card reference), so split at each seticon: text segments go through the real
        # builder (which merges runs, detects icons/links/red), the seticon becomes its own run.
        if not any(s.get('font') == _SETICON_FONT for s in spans):
            return orig_build(spans, reds)
        out, buf = [], []
        for s in spans:
            if s.get('font') == _SETICON_FONT:
                if buf:
                    out.extend(orig_build(buf, reds))
                    buf = []
                out.append({'kind': 'seticon', 'fp': s['_fp']})
            else:
                buf.append(s)
        if buf:
            out.extend(orig_build(buf, reds))
        return out

    orig_cols = pg.column_edges
    pg.collect_lines = collect
    pg.build_runs = build
    # Detect columns the support-aware way for the FAQ: its Q&A/rulings pages are single-column but
    # peppered with wrapped card references, which the plain detector mistook for a right column and
    # scrambled (splitting questions into "( 96)?" fragments). The Grimoire keeps the plain detector.
    pg.column_edges = pg.column_edges_dense
    # A bullet the publisher sets partly in italic lands in its own PDF text block, so the
    # continuation reads as an orphan paragraph starting mid-sentence ("if playing with the
    # Current Environment…"). The FAQ asks the parser to rejoin those by geometry; the Grimoire,
    # whose parse is measured against its printed page, keeps the plain block rule.
    orig_fold = pg.FOLD_BULLET_CONTINUATION
    pg.FOLD_BULLET_CONTINUATION = True
    try:
        nodes, doc = pg.parse_pdf(pdf, {})
    finally:
        pg.collect_lines = orig_collect
        pg.build_runs = orig_build
        pg.column_edges = orig_cols
        pg.FOLD_BULLET_CONTINUATION = orig_fold
    return nodes, doc, captured.get('svgs', {})


def _page_spans(page):
    spans = []
    for b in page.get_text('dict')['blocks']:
        if 'lines' not in b:
            continue
        for l in b['lines']:
            for s in l['spans']:
                if s['text'].strip():
                    spans.append(s)
    spans.sort(key=lambda s: (round(s['bbox'][1] / 3.0), s['bbox'][0]))
    return spans


def _card_name(pre, stops):
    """The card name at the end of the text before '(', named exactly as cardlinks would:
    the trailing capitalised name, with any leading question/stop word dropped."""
    m = _TRAILING_NAME.search(pre.rstrip())
    if not m:
        return ''
    _lead, link = cardlinks._split_name(m.group(1), stops)
    return _fold_name(link)


def write_svgs(svgs, outdir=FAQSETS_DIR):
    """Write each mark once. The filename IS the shape's fingerprint, so a file that is
    already there is already this mark — and rewriting it would only swap one edition's
    rounding for another's. The German and Italian books draw the same art a hundredth
    of a point off the Spanish one, which rewrote 150 identical files on every build and
    made the result depend on which language happened to be built last."""
    os.makedirs(outdir, exist_ok=True)
    written = 0
    for fp, svg in svgs.items():
        path = os.path.join(outdir, fp + '.svg')
        if os.path.exists(path):
            continue
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg + '\n')
        written += 1
    return written


# ---- the icon-reference chapter (the campaign/product/starter/promo tables) --
PRODUCTS_DIR = os.path.join(langpack.ROOT, 'assets', 'products')
ICONS_DIR = os.path.join(langpack.ROOT, 'assets', 'icons')
CORESET_ART = 'faq-coreset'            # the core set's icon is the elder-sign glyph, not vector
# A row whose mark the page defeats the tracer on, answered with the real vector instead. The
# "Return to the Night of the Zealot" mark is a white star knocked OUT of a filled disc: tracing
# the page's filled paths yields the disc alone (a black blob), because the star is a hole, not a
# path. Its true vector is cut from the artist's symbol sheet by tools/scenario_icons.py.
# Keyed by the folded product name, so it answers in every language.
ICONREF_OVERRIDES = {
    'regreso a la noche de la fanatica': 'return-night-of-the-zealot',
    'return to the night of the zealot': 'return-night-of-the-zealot',
}
_HEAD_MIN = 15.0                       # a group heading is Teutonic and at least this big
_COL_SPLIT = 260.0                     # left/right column boundary on the two-up icon page


def _icon_left(page, name_x, y0, y1, col_left):
    """Union bbox of the dark filled paths between the column's left edge and the name —
    the product's icon sits to the left of its name."""
    xs = []
    for d in page.get_drawings():
        if not ir._filled(d):
            continue
        r = d['rect']
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if col_left - 2 <= cx < name_x - 0.5 and y0 - 2 <= cy <= y1 + 2:
            xs.append((r.x0, r.y0, r.x1, r.y1))
    if not xs:
        return None
    return (min(b[0] for b in xs), min(b[1] for b in xs),
            max(b[2] for b in xs), max(b[3] for b in xs))


def extract_iconref(pdf_path):
    """The icon-reference tables that close the FAQ: campaigns, standalone products,
    starter decks and promos, each a name with the product's vector icon beside it.

    Returns (groups, svgs): groups = [{'title','level','blurb','items':[{'name','art'}]}]
    in the Grimoire's icon-chapter shape; svgs = {art_id: svg} to write into assets/products/.
    The reader gets a searchable table instead of a flattened, uncopyable picture.

    The tables are at the back, but not every edition puts them on the very last page: the
    Italian FAQ closes with a chaos-token key and prints its tables on the page before, which
    read as the last page gave that language an empty chapter and stripped the product marks
    off its taboo list. So the closing pages are tried from the back and the first that yields
    a table wins — the page says whether it holds one, rather than the pack naming a number."""
    doc = fitz.open(pdf_path)
    for pno in range(doc.page_count - 1, max(doc.page_count - 4, 0) - 1, -1):
        groups, svgs = _iconref_page(doc[pno])
        if groups:
            return groups, svgs, pno + 1
    return [], {}, None


def _iconref_page(page):
    """Read the icon tables off one page -> (groups, svgs); ([], {}) if it holds none."""
    # icon-font glyphs on the page (the core set's mark is one) — kept to spot a product whose
    # icon is a glyph rather than vector art, since it sits on its own line beside the name.
    glyph_boxes = [s['bbox'] for b in page.get_text('dict')['blocks'] if 'lines' in b
                   for l in b['lines'] for s in l['spans'] if pg.is_icon_font(s.get('font', ''))]
    rows = []                          # (col, y, x, is_head, text, spans, y1)
    for b in page.get_text('dict')['blocks']:
        if 'lines' not in b:
            continue
        for l in b['lines']:
            # Drop any icon-font glyph char (private-use area): a couple of names carry the
            # core-set glyph, which would otherwise render as a tofu box in the text.
            txt = re.sub('[-]', '', ''.join(s['text'] for s in l['spans'])).strip()
            if not txt or txt.isdigit() or 'PREGUNTAS' in txt or 'FREQUENTLY' in txt.upper():
                continue                # page number / running header
            x0, y0, y1 = l['bbox'][0], l['bbox'][1], l['bbox'][3]
            is_head = any('Teutonic' in s['font'] and s['size'] >= _HEAD_MIN for s in l['spans'])
            # Column by a coarse x bucket, not a single left/right split: the English page sets
            # two heading columns on its right half ("Campaign …" beside "Standalone …"), which a
            # 2-column model interleaves and mis-merges. ~120pt keeps each heading with its items.
            rows.append((int(x0 / 120), round(y0), x0, is_head, txt, l['spans'], y1))
    rows.sort()

    groups = []
    svgs = {}
    cur = {}                           # the open group per column bucket
    lasthead = {}                      # (y0, y1) of the last heading line per column, for wrap-merge
    lastitem = {}                      # (item, x, y1) of the last product row per column
    for col, y, x, is_head, txt, spans, y1 in rows:
        if is_head:
            g = cur.get(col)
            prev = lasthead.get(col)
            # A heading that wrapped onto a second line: only merge when the two lines are
            # vertically adjacent — otherwise two separate group headings ("Campaign Product
            # Icons" then "Standalone Product Icons") would fuse into one.
            if (g is not None and g.get('_wrap') and not g['items'] and not g['blurb']
                    and prev is not None and -8 <= y - prev[1] < 20):
                g['title'] += ' ' + txt
                # re-evaluate on the full title: "Current, Legacy, and Limited" only reads
                # as the environments block once its second line "Environments (Beta)" joins.
                g['_skip'] = bool(re.search(r'entorno|environment', langpack.fold(g['title'])))
                lasthead[col] = (y, y1)
                continue
            # The environments variant lists starter decks in prose with inline icons — not an
            # icon table. Mark its group to swallow everything under it, so those inline icons
            # are not mistaken for product entries.
            skip = bool(re.search(r'entorno|environment', langpack.fold(txt)))
            g = {'title': txt, 'level': 1, 'blurb': '', 'items': [], '_wrap': True, '_skip': skip}
            groups.append(g)
            cur[col] = g
            lasthead[col] = (y, y1)
            continue
        g = cur.get(col)
        if g is None or g.get('_skip'):
            continue
        g['_wrap'] = False
        box = _icon_left(page, x, y, y1, x - 22.0)   # the icon sits just left of the name
        # A product name too long for its column runs onto a second line — and that line starts
        # further LEFT than the first, because the first was pushed right to clear the icon and
        # the second has no icon to clear. Six English products were shipped cut in half by
        # this ("Edge of the Earth (Investigator", with "Expansion)" lost into the group's
        # blurb), and the two Hemlock Vale rows lost the very words that tell them apart.
        prev = lastitem.get(col)
        if (box is None and prev is not None and prev[0] in g['items']
                and -3 <= y - prev[2] < 8 and x <= prev[1] + 1
                and (prev[0]['name'].count('(') != prev[0]['name'].count(')')
                     or txt.startswith('('))):
            prev[0]['name'] = (prev[0]['name'] + ' ' + txt).strip()
            lastitem[col] = (prev[0], prev[1], y1)
            continue
        namey = bool(re.match(r'^[“"A-ZÁÉÍÓÚÜÑ]', txt)) and len(txt) <= 62
        # The core set's icon is a font glyph (the elder-sign mark), not vector art — so an
        # item with a glyph to its left but no traced box is still a product ("Caja básica"),
        # and must not be mistaken for the group's descriptive blurb.
        glyph_left = any(gb[2] <= x + 1 and abs((gb[1] + gb[3]) / 2 - (y + y1) / 2) < 6
                         for gb in glyph_boxes)
        if box is None and glyph_left and namey:
            g['items'].append({'name': txt, 'art': CORESET_ART})
            lastitem[col] = (g['items'][-1], x, y1)
            continue
        # A product entry is a short, capitalised name with a small square-ish icon to its
        # left. Anything else on the page (a sentence of the environments prose that happens
        # to carry an inline icon) fails one of these and is treated as descriptive text.
        square = box is not None and 3 <= (box[2] - box[0]) <= 18 and \
            0.3 <= (box[2] - box[0]) / max(box[3] - box[1], 0.1) <= 2.6
        if box is None or not (square and namey):
            g['blurb'] = (g['blurb'] + ' ' + txt).strip()   # a descriptive line, not a product
            continue
        svg = ir.icon_svg(page, box)
        fp = _fingerprint(svg)
        art = ''
        if fp and svg:
            art = 'fc-' + fp[1:] if fp.startswith('e') else fp
            svgs[art] = svg
        over = ICONREF_OVERRIDES.get(langpack.fold(txt))
        if over:
            art = over                    # the page defeats the tracer here; use the real vector
        g['items'].append({'name': txt, 'art': art})
        lastitem[col] = (g['items'][-1], x, y1)
    for g in groups:
        g.pop('_wrap', None); g.pop('_skip', None)
    groups = [g for g in groups if g['items']]           # keep only real icon tables
    # The core-set icon is the elder-sign glyph (already rendered as a game icon); reuse it.
    if any(it['art'] == CORESET_ART for g in groups for it in g['items']):
        eld = os.path.join(ICONS_DIR, 'eldersign.svg')
        if os.path.exists(eld):
            svgs[CORESET_ART] = open(eld, encoding='utf-8').read().strip()
    return groups, svgs


def write_products(svgs, outdir=PRODUCTS_DIR):
    """Trace each product's mark once, for the same reason as write_svgs: a product's
    mark is the same drawing whichever edition it was traced from. Every edition rounds
    it a hundredth of a point differently (41 of 50 marks re-traced from the German and
    Italian books differ by no more than 0.02), so rewriting would churn the art on every
    build and leave whichever language ran last as the winner. To re-trace one on purpose,
    delete it and build again."""
    os.makedirs(outdir, exist_ok=True)
    written = 0
    for art, svg in svgs.items():
        path = os.path.join(outdir, art + '.svg')
        if os.path.exists(path):
            continue
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg + '\n')
        written += 1
    return written


def report_orphans(quiet=False):
    """Traced marks on disk that no built corpus refers to any more.

    Every build WRITES the art it traced and none of them ever removes any, so a change to how
    the marks are traced leaves the old fingerprints behind — 183 of them, after one experiment
    here. Reported rather than deleted: a partial build (one language, or one that failed part
    way) legitimately refers to fewer marks than the repo holds, and quietly deleting the rest
    would turn a half-finished run into a destructive one."""
    import glob
    import json as _json
    used = set()
    for path in glob.glob(os.path.join(langpack.DATA_DIR, 'faq_*.json')) + \
            glob.glob(os.path.join(langpack.DATA_DIR, 'grimoire_*.json')):
        with open(path, encoding='utf-8') as f:
            data = _json.load(f)

        def runs_of(sections):
            for s in sections:
                for b in s.get('intro') or []:
                    yield b.get('runs') or []
                for e in s.get('entries') or []:
                    if e.get('titleRuns'):
                        yield e['titleRuns']
                    for b in e.get('blocks') or []:
                        yield b.get('runs') or []
                ub = s.get('ub') or {}
                for bucket in ('ultimatums', 'boons', 'refractions'):
                    for it in ub.get(bucket) or []:
                        for b in it.get('blocks') or []:
                            yield b.get('runs') or []
        for runs in runs_of(data.get('sections') or []):
            for r in runs:
                if r.get('kind') == 'seticon' and r.get('fp'):
                    used.add(r['fp'])
    have = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(FAQSETS_DIR, '*.svg'))}
    orphans = sorted(have - used)
    if orphans and not quiet:
        print(f'  [warn] {len(orphans)} traced mark(s) in assets/faqsets/ are no longer referenced '
              f'by any corpus — delete them before committing if this was a full build:',
              file=sys.stderr)
        print('         ' + ', '.join(orphans[:8]) + (' …' if len(orphans) > 8 else ''), file=sys.stderr)
    return orphans
