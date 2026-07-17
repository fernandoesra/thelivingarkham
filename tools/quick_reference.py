# -*- coding: utf-8 -*-
"""Rip the symbol colours off the Quick Reference page.

The book prints its symbol key as small colour badges — a blue Guardian shield, an amber
Seeker lamp, and so on — embedded as raster images. On paper the colour is decoration;
on the site it is data, because it is how a reader tells a Guardian card from a Mystic
one at a glance. So each badge's brand colour is read straight off its own pixels.

This is a STARTING POINT, not a source of truth, and the difference matters. The badges
are ~50px anti-aliased CMYK thumbnails, so the read is noisy: the hue comes out right
every time, but the exact value drifts — the Seeker highlight reads pale, the Skull
shadow reads dark, and the two editions do NOT agree to the byte (run it on es and en and
compare). So its output is reviewed by eye and pasted into the stylesheet as --sym-*
custom properties, where a colour is meant to be edited; it is never written to a pack or
consumed by the render. The authority on these colours is the game, not this rip.

Usage:  python tools/quick_reference.py [es|en]      # prints the palette it reads
"""
import sys
import colorsys
import collections
import fitz

import langpack
import parse_grimoire as P

# Which embedded badge is which symbol, by the section heading it sits beside. Filled in
# per edition below from the page geometry — the xref numbers are not stable across PDFs,
# so they are found, not hard-coded.
SYMBOLS = [
    ('classes', ['guardian', 'seeker', 'mystic', 'rogue', 'survivor']),
    ('skills', ['willpower', 'intellect', 'combat', 'agility', 'wild']),
    ('tokens', ['eldersign', 'autofail', 'skull', 'cultist', 'tablet', 'elderthing']),
]


def _brand(pm):
    """The badge's brand hue, read from its pixels.

    Not the average — a badge is a colour on a light shield with a dark outline, and the
    mean of those is mud. The dominant saturated hue is the brand colour; a bright, not a
    shadowed, representative of it is returned so it reads as the colour the eye sees."""
    if pm.colorspace and pm.colorspace.n >= 4:      # the badges are CMYK
        pm = fitz.Pixmap(fitz.csRGB, pm)
    hues = collections.defaultdict(list)
    px = pm.samples
    step = pm.n
    for i in range(0, len(px) - step + 1, step):
        r, g, b = px[i], px[i + 1], px[i + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.28 or v < 0.28:                    # skip outline, shadow and parchment
            continue
        hues[round(h * 18)].append((s * v, r, g, b))
    if not hues:
        return None
    dom = max(hues, key=lambda k: len(hues[k]))
    lit = sorted(hues[dom])
    r, g, b = lit[int(len(lit) * 0.9)][1:]
    return '#%02x%02x%02x' % (r, g, b)


def _badges(page, clip):
    """The colour-badge images on the page, top to bottom in their own column.

    The symbol column runs down the right of the sheet; each row prints a colour badge to
    the left of a black glyph. The badges are the only small images, so filtering to small
    ones and reading top-to-bottom pairs them with SYMBOLS by position.

    The x-band is taken from the figure's own clip, not hard-coded: an edition that prints
    two book pages on one PDF page (the English spread) puts the sheet on the right half,
    so the badges sit ~612pt further right than in the single-page Spanish edition."""
    x0, x1 = (clip[0], clip[2]) if clip else (page.rect.x0, page.rect.x1)
    w = x1 - x0
    lo, hi = x0 + w * 0.62, x0 + w * 0.80        # the badge column, as a fraction of the sheet
    imgs = [im for im in page.get_image_info(xrefs=True)
            if lo < im['bbox'][0] < hi and im['width'] < 80 and im['height'] < 80]
    imgs.sort(key=lambda im: im['bbox'][1])
    return imgs


def palette(pack):
    doc = fitz.open(pack.require_pdf())
    # the sheet is the section declared "kind": "quickref"
    names = [n for sc in pack.sections if sc.get('kind') == 'quickref'
             for n in sc.get('figures', [])]
    byname = {f['name']: f for f in pack.figures}
    pages = sorted({byname[n]['page'] for n in names if n in byname})
    if not pages:
        return {}
    page = doc[pages[0] - 1]
    clip = next((f.get('clip') for n in names for f in [byname.get(n)] if f and f.get('clip')), None)
    badges = _badges(page, clip)
    want = [n for _, group in SYMBOLS for n in group]
    if len(badges) != len(want):
        print(f'  [quickref] {pack.code}: found {len(badges)} badges, expected {len(want)} '
              f'— layout not recognised, skipping', file=sys.stderr)
        return {}
    out = {}
    for name, im in zip(want, badges):
        out[name] = _brand(fitz.Pixmap(doc, im['xref']))
    return out


def _sheet_page_clip(pack):
    """The Quick Reference sheet's page and figure clip, or (None, None)."""
    byname = {f['name']: f for f in pack.figures}
    for sc in pack.sections:
        if sc.get('kind') == 'quickref':
            for n in sc.get('figures', []):
                f = byname.get(n)
                if f:
                    return f['page'], f.get('clip')
    return None, None


def prose(pack):
    """The sheet's text sub-sections, in order, with their icons kept.

    The sheet is prose down its left column and a symbol grid down its right. Read in
    reading order the two interleave — the action-type list is split in half by the
    chaos-token names that sit beside it — so the prose is taken by COLUMN instead: only
    the left half of the sheet, which is nothing but the four text sub-sections.

    Reuses the book parser's own line collection and run building, so an inline icon in
    the prose ("Fight: ... using [combat]") survives as an icon and every term is later
    autolinked to the glossary exactly as a chapter's prose is. Nothing is matched by
    wording; the headings are found by their face, the prose by its position.

    -> [{'title': str, 'blocks': [...]}], one per sub-heading on the sheet."""
    page, clip = _sheet_page_clip(pack)
    if page is None:
        return []
    x0 = clip[0] if clip else 0.0
    x1 = clip[2] if clip else None
    lines, doc = P.collect_lines(pack.require_pdf(), P.masks_for(pack))
    if x1 is None:
        x1 = doc[page - 1].rect.x1
    reds = P.learn_reds(lines)
    mid = x0 + (x1 - x0) * 0.47              # the prose column is the sheet's left half
    page_obj = doc[page - 1]

    # The last text block on the sheet — the action types — runs the full width in two
    # mini-columns, so its right half sits in the symbol column, UNDER the symbol grid.
    # The badges give the grid's floor: right-half prose below the lowest badge is that
    # footer, and nothing else is (the symbols are all above it). Without this the two
    # right-column action types are lost to the same jumble that splits them in the parse.
    badges = _badges(page_obj, clip)
    floor = max((im['bbox'][3] for im in badges), default=0.0)

    def as_body(ln):
        return {'block': ln['block'], 'bullet': P.bullet_level(ln),
                'runs': P.merge_runs(P.build_runs(ln['spans'], reds)), 'page': ln['page']}

    # The left column, whole, top to bottom — NOT merged with the footer by y. Sorting the
    # two columns together by height would slot a footer line between a paragraph and its
    # own wrapped continuation and orphan it ("...capacidad de" | "carta").
    left = sorted((ln for ln in lines if ln['page'] == page and x0 - 1 <= ln['x0'] < mid),
                  key=lambda ln: round(ln['y']))
    # The action-types footer: right-half prose below every badge, in its own reading order.
    footer = sorted((ln for ln in lines if ln['page'] == page and ln['x0'] >= mid and ln['y'] > floor),
                    key=lambda ln: round(ln['y']))

    out, raw = [], []

    def flush():
        if out and raw:
            out[-1]['blocks'] = P.finalize_body(raw)

    for ln in left:
        lvl = P.line_is_heading(ln)
        if lvl is not None and lvl <= 2:        # 18.9pt sheet title: not a sub-section
            continue
        if lvl is not None:                     # a sub-section heading (~14.7pt -> lvl 3)
            flush(); raw = []
            out.append({'title': P.line_text(ln).strip(' .'), 'blocks': []})
            continue
        if not out:                             # body before the first heading: ignore
            continue
        raw.append(as_body(ln))
    # The footer belongs to the last (bottom) section — the action types it continues.
    raw.extend(as_body(ln) for ln in footer)
    flush()
    return [s for s in out if s['blocks']]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    codes = sys.argv[1:] or [langpack.DEFAULT_LANG]
    for code in codes:
        pack = langpack.load(code)
        pal = palette(pack)
        print(f'== {code}: {len(pal)} symbol colour(s)')
        for _, group in SYMBOLS:
            for n in group:
                print(f'  --sym-{n}:{pal.get(n, "?")};')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
