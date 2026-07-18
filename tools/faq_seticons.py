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
            rows.append((0 if x0 < _COL_SPLIT else 1, round(y0), x0, is_head, txt, l['spans'], y1))
    rows.sort()

    groups = []
    svgs = {}
    cur = {0: None, 1: None}           # the open group per column
    lasthead = {0: None, 1: None}      # (y0, y1) of the last heading line, for wrap-merge
    for col, y, x, is_head, txt, spans, y1 in rows:
        if is_head:
            g = cur[col]
            prev = lasthead[col]
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
        g = cur[col]
        if g is None or g.get('_skip'):
            continue
        g['_wrap'] = False
        col_left = 36.0 if col == 0 else 268.0
        box = _icon_left(page, x, y, y1, col_left)
        # A product entry is a short, capitalised name with a small square-ish icon to its
        # left. Anything else on the page (a sentence of the environments prose that happens
        # to carry an inline icon) fails one of these and is treated as descriptive text.
        square = box is not None and 3 <= (box[2] - box[0]) <= 18 and \
            0.3 <= (box[2] - box[0]) / max(box[3] - box[1], 0.1) <= 2.6
        namey = bool(re.match(r'^[“"A-ZÁÉÍÓÚÜÑ]', txt)) and len(txt) <= 62
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
    return groups, svgs


def write_products(svgs, outdir=PRODUCTS_DIR):
    os.makedirs(outdir, exist_ok=True)
    for art, svg in svgs.items():
        with open(os.path.join(outdir, art + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg + '\n')
    return len(svgs)
