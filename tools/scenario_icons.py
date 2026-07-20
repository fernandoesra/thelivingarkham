# -*- coding: utf-8 -*-
"""Cut the individual scenario (encounter-set) symbols out of the artist's per-campaign SVG sheets.

A chapter-1 refraction belongs to a scenario, and the printed card carries that scenario's
encounter-set symbol in the diamond above its type line. Those symbols are not in the FAQ (its
icon reference only lists campaign/product marks), so they come from the vector symbol sheets kept
beside the project art. Each sheet is a grid of unlabelled marks; this file records WHICH mark on
WHICH sheet is which scenario (identified from the reference photos), clusters that mark's filled
paths, and traces it into the same 0..100 viewBox SVG every other product icon uses — so it is a
crisp, recolourable mask, not a bitmap trace.

Run after adding a sheet or a new refraction:  python tools/scenario_icons.py
Writes assets/products/<art>.svg. The art ids are wired to refractions in tools/ub_refractions.json.
"""
import os
import sys

import fitz

import icon_reference as ir
import langpack

SHEETS = os.path.join('C:', os.sep, 'Users', 'Fernando', 'Mi unidad', 'Rincon Miskatonic',
                      'Contenido AH LCG', 'Iconos Arkham')
PRODUCTS = os.path.join(langpack.ROOT, 'assets', 'products')
_PREFIX = 'Arkham Horror LCG Symbols - Main Sets - '

# art id -> (sheet campaign, index into the sheet's clustered symbols in reading order, what it is)
# The index is stable for a given sheet file; re-check with tools/scenario_icons.py --contact <sheet>
# if the artist ever re-exports one.
PICKS = {
    'scen-undimensioned-and-unseen': ('The Dunwich Legacy', 16, 'Invisibles y sin dimension / Undimensioned and Unseen'),
    'scen-the-pallid-mask':          ('The Path to Carcosa', 17, 'La mascara palida / The Pallid Mask'),
    'scen-horror-in-high-gear':      ('The Innsmouth Conspiracy', 8, 'Horror a toda maquina / Horror in High Gear'),
    'scen-into-the-maelstrom':       ('The Innsmouth Conspiracy', 10, 'Hacia el remolino / Into the Maelstrom'),
    'scen-where-the-gods-dwell':     ('The Dream Eaters', 17, 'Donde moran los dioses / Where the Gods Dwell'),
    'scen-shades-of-suffering':      ('The Scarlet Keys', 18, 'Sombras de sufrimiento / Shades of Suffering'),
    'scen-fate-of-the-vale':         ('The Feast of Hemlock Vale', 6, 'El destino del Valle / Fate of the Vale'),
    'scen-doom-of-arkham-2':         ('The Drowned City', 26, 'La perdicion de Arkham II / The Doom of Arkham Pt II'),
    # Not a scenario: the "Return to" campaign mark the FAQ's own icon table traces as a bare disc.
    'return-night-of-the-zealot':    ('Core Game & Set', 51, 'Regreso a La noche de la fanatica / Return to the Night of the Zealot'),
}


def _sheet_path(campaign):
    return os.path.join(SHEETS, _PREFIX + campaign + '.svg')


def symbols(page, gap=4.0, lo=6.0, hi=90.0):
    """Every mark on the sheet, as a box, in reading order (row, then left to right).

    The marks are dark filled vector art, so the filled paths are clustered by proximity (one
    cluster = one symbol) exactly as the FAQ's inline icons are, then filtered to a plausible
    symbol size so stray rules and the sheet's headings do not count as marks."""
    rects = []
    for d in page.get_drawings():
        if not ir._filled(d):
            continue
        r = d['rect']
        if r.width <= 0 or r.height <= 0 or r.width > 120 or r.height > 120:
            continue
        rects.append([r.x0, r.y0, r.x1, r.y1])
    n = len(rects)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        a = rects[i]
        for j in range(i + 1, n):
            b = rects[j]
            if not (a[0] > b[2] + gap or b[0] > a[2] + gap or a[1] > b[3] + gap or b[1] > a[3] + gap):
                pi, pj = find(i), find(j)
                if pi != pj:
                    parent[pi] = pj
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(rects[i])
    out = []
    for g in groups.values():
        box = (min(r[0] for r in g), min(r[1] for r in g),
               max(r[2] for r in g), max(r[3] for r in g))
        w, h = box[2] - box[0], box[3] - box[1]
        if lo <= max(w, h) <= hi:
            out.append(box)
    out.sort(key=lambda b: (round(b[1] / 12.0), b[0]))
    return out


def build(quiet=False):
    os.makedirs(PRODUCTS, exist_ok=True)
    by_sheet = {}
    for art, (campaign, idx, what) in PICKS.items():
        by_sheet.setdefault(campaign, []).append((art, idx, what))
    written, missing = 0, []
    for campaign, picks in sorted(by_sheet.items()):
        path = _sheet_path(campaign)
        if not os.path.exists(path):
            missing.append(campaign)
            continue
        page = fitz.open(path)[0]
        boxes = symbols(page)
        for art, idx, what in picks:
            if idx >= len(boxes):
                missing.append(f'{campaign}#{idx}')
                continue
            svg = ir.icon_svg(page, boxes[idx])
            if not svg:
                missing.append(f'{campaign}#{idx} (empty trace)')
                continue
            with open(os.path.join(PRODUCTS, art + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(svg + '\n')
            written += 1
            if not quiet:
                print(f'  {art:32} <- {campaign} #{idx}   ({what})')
    if not quiet:
        print(f'  {written} scenario icon(s) -> assets/products/')
        if missing:
            print(f'  [warn] not built: {", ".join(missing)}', file=sys.stderr)
    return written


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build()
    return 0


if __name__ == '__main__':
    sys.exit(main())
