# -*- coding: utf-8 -*-
"""Group the set icons that are the SAME product mark traced slightly differently.

Every "( <icon> 20)" in the books is traced off the page and fingerprinted by shape
(faq_seticons._fingerprint), which is what collapses ~500 marks onto a few dozen products. It is
a *quantised* fingerprint, though, so a mark the page rendered a hair differently — a path the
tracer split, a coordinate that rounded the other way — lands on a neighbouring hash: 179 distinct
fingerprints for 59 real products. That is harmless while the icon is only ever drawn (they all
look the same), but useless for *identifying* the product, which is what the ArkhamDB resolver
needs: 46 near-identical hashes each learn their product separately, and most learn nothing at all.

So the traced SVGs are compared as pictures instead of hashes: each is rendered to a small
bitmap and grouped with any other whose bitmap differs in only a handful of pixels. The grouping
is checkable — the resolver reports any group whose references disagree about which product it
is, which is exactly what over-merging two different marks would look like.
"""
import glob
import os

import fitz

import langpack

FAQSETS_DIR = os.path.join(langpack.ROOT, 'assets', 'faqsets')
_N = 24                                # bitmap side; big enough to tell the marks apart
_TOL = 30                              # pixels that may differ (of 576) and still be the same mark


def _bitmap(svg_text):
    doc = fitz.open('svg', svg_text.encode())
    page = doc[0]
    m = fitz.Matrix(_N / page.rect.width, _N / page.rect.height)
    pix = page.get_pixmap(matrix=m, alpha=False, colorspace=fitz.csGRAY)
    return bytes(1 if b < 128 else 0 for b in pix.samples)


def groups(directory=FAQSETS_DIR):
    """{fingerprint: group_id} over every traced set icon on disk.

    The group id is the alphabetically first fingerprint in the group, so it is stable across
    builds as long as the art is (a new mark can only ever start a new group or join one)."""
    bits = {}
    for path in sorted(glob.glob(os.path.join(directory, '*.svg'))):
        fp = os.path.basename(path)[:-4]
        try:
            with open(path, encoding='utf-8') as f:
                bits[fp] = _bitmap(f.read())
        except Exception:
            continue                   # an unreadable trace simply stays on its own
    buckets = []                       # [(representative_bitmap, [fp, …]), …]
    for fp in sorted(bits):
        b = bits[fp]
        for rep, members in buckets:
            if sum(x != y for x, y in zip(b, rep)) <= _TOL:
                members.append(fp)
                break
        else:
            buckets.append((b, [fp]))
    out = {}
    for _rep, members in buckets:
        gid = members[0]
        for fp in members:
            out[fp] = gid
    return out
