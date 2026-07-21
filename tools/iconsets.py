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


def bitmaps(directory):
    """{name: bitmap} for every traced mark in a directory.

    The key is the filename stem — a fingerprint under assets/faqsets/, an art id under
    assets/products/."""
    out = {}
    for path in sorted(glob.glob(os.path.join(directory, '*.svg'))):
        try:
            with open(path, encoding='utf-8') as f:
                out[os.path.basename(path)[:-4]] = _bitmap(f.read())
        except Exception:
            continue                   # an unreadable trace simply stays on its own
    return out


def same_picture(bits, pool, tol=_TOL):
    """The entry of `pool` that is the same picture as `bits`, or None.

    groups() asks this of one directory against itself; this asks it of two, which is the only
    reason the marks printed in the prose and the marks printed in the books' own icon LEGEND
    had never been compared — they live in different directories. Same bitmap, same tolerance:
    a mark either is a drawing we already hold or it is not, and which folder the drawing came
    from does not change the answer."""
    best = None
    for name, b in pool.items():
        d = sum(x != y for x, y in zip(bits, b))
        if d <= tol and (best is None or d < best[0]):
            best = (d, name)
    return best[1] if best else None


def groups(directory=FAQSETS_DIR):
    """{fingerprint: group_id} over every traced set icon on disk.

    The group id is the alphabetically first fingerprint in the group, so it is stable across
    builds as long as the art is (a new mark can only ever start a new group or join one)."""
    bits = bitmaps(directory)
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
