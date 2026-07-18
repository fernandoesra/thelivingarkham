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


def _inject_icons(lines, doc, skip_pages=()):
    """Slot every page's icons into the line stream as one-glyph pseudo-lines, positioned so
    the parser joins each into the paragraph it interrupts. Returns {fingerprint: svg}."""
    by_page = {}
    for l in lines:
        by_page.setdefault(l['page'], []).append(l)
    svgs = {}
    added = []
    for pno in range(doc.page_count):
        if (pno + 1) in skip_pages:
            continue
        page = doc[pno]
        plines = by_page.get(pno + 1, [])
        for box, svg, fp in _cluster_icons(page):
            svgs.setdefault(fp, svg)
            icx, icy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            # the line this icon interrupts: same row, its text ending just left of the icon
            host, hostd = None, 1e9
            for l in plines:
                if abs((l['y'] + l['y1']) / 2.0 - icy) > 6:
                    continue
                lx1 = max(s['bbox'][2] for s in l['spans'])
                if lx1 <= icx + 3 and (icx - lx1) < hostd:
                    hostd, host = icx - lx1, l
            span = {'font': _SETICON_FONT, 'text': '', '_fp': fp,
                    'bbox': (box[0], box[1], box[2], box[3]), 'size': 10.0, 'color': 0}
            added.append({'page': pno + 1, 'col': host['col'] if host else 0, 'xedge': 0,
                          'y': box[1], 'y1': box[3], 'x0': box[0], 'spans': [span],
                          'block': host['block'] if host else -1})
    lines.extend(added)
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


def parse_with_icons(pdf, skip_pages=()):
    """parse_grimoire.parse_pdf, but with the FAQ's vector set icons recovered and slotted
    back into the text. Returns (nodes, doc, svgs). Done by patching the two module hooks
    the parser resolves at call time — collect_lines (to inject the icons) and build_runs
    (to turn an injected icon span into a `seticon` run) — so the parser is reused wholesale."""
    orig_collect = pg.collect_lines
    orig_build = pg.build_runs
    captured = {}

    def collect(pdf_, masks):
        lines, doc = orig_collect(pdf_, masks)
        captured['svgs'] = _inject_icons(lines, doc, skip_pages)
        return lines, doc

    def build(spans, reds=pg._KEEP):
        if spans and all(s.get('font') == _SETICON_FONT for s in spans):
            return [{'kind': 'seticon', 'fp': s['_fp']} for s in spans]
        return orig_build(spans, reds)

    pg.collect_lines = collect
    pg.build_runs = build
    try:
        nodes, doc = pg.parse_pdf(pdf, {})
    finally:
        pg.collect_lines = orig_collect
        pg.build_runs = orig_build
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


def extract(pdf_path, stops=frozenset()):
    """Scan the FAQ PDF. Returns (svgs, keymap):
        svgs   = {fingerprint: svg_text}
        keymap = {(folded_card_name, number): fingerprint}
    The name is the card named just before '(', the number the run just after it."""
    doc = fitz.open(pdf_path)
    svgs = {}
    keymap = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        spans = _page_spans(page)
        for i in range(len(spans) - 1):
            s0, s1 = spans[i], spans[i + 1]
            t0, t1 = s0['text'].rstrip(), s1['text'].lstrip()
            if not (t0.endswith('(') and _NUM.match(t1)):
                continue
            if abs(s0['bbox'][1] - s1['bbox'][1]) > 4:
                continue
            gx0, gx1 = s0['bbox'][2], s1['bbox'][0]
            if gx1 - gx0 < 3:
                continue                         # "(3)" with no icon
            box = _tight_box(page, gx0, gx1,
                             min(s0['bbox'][1], s1['bbox'][1]),
                             max(s0['bbox'][3], s1['bbox'][3]))
            if box is None:
                continue
            svg = ir.icon_svg(page, box)
            fp = _fingerprint(svg)
            if not fp:
                continue
            svgs.setdefault(fp, svg)
            pre = s0['text'][:s0['text'].rstrip().rfind('(')]
            name = _card_name(pre, stops)
            num = _NUM.match(t1).group(1)
            if name:
                keymap[(name, num)] = fp
    return svgs, keymap


def write_svgs(svgs, outdir=FAQSETS_DIR):
    os.makedirs(outdir, exist_ok=True)
    for fp, svg in svgs.items():
        with open(os.path.join(outdir, fp + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg + '\n')
    return len(svgs)


# ---- the icon-reference chapter (the campaign/product/starter/promo tables) --
PRODUCTS_DIR = os.path.join(langpack.ROOT, 'assets', 'products')
ICONS_DIR = os.path.join(langpack.ROOT, 'assets', 'icons')
CORESET_ART = 'faq-coreset'            # the core set's icon is the elder-sign glyph, not vector
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
    """The icon-reference tables on the FAQ's last page: campaigns, standalone products,
    starter decks and promos, each a name with the product's vector icon beside it.

    Returns (groups, svgs): groups = [{'title','level','blurb','items':[{'name','art'}]}]
    in the Grimoire's icon-chapter shape; svgs = {art_id: svg} to write into assets/products/.
    The reader gets a searchable table instead of a flattened, uncopyable picture."""
    doc = fitz.open(pdf_path)
    page = doc[doc.page_count - 1]
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
        namey = bool(re.match(r'^[“"A-ZÁÉÍÓÚÜÑ]', txt)) and len(txt) <= 62
        # The core set's icon is a font glyph (the elder-sign mark), not vector art — so an
        # item with a glyph to its left but no traced box is still a product ("Caja básica"),
        # and must not be mistaken for the group's descriptive blurb.
        glyph_left = any(gb[2] <= x + 1 and abs((gb[1] + gb[3]) / 2 - (y + y1) / 2) < 6
                         for gb in glyph_boxes)
        if box is None and glyph_left and namey:
            g['items'].append({'name': txt, 'art': CORESET_ART})
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
        g['items'].append({'name': txt, 'art': art})
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
    os.makedirs(outdir, exist_ok=True)
    for art, svg in svgs.items():
        with open(os.path.join(outdir, art + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg + '\n')
    return len(svgs)
