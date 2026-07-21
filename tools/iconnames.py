# -*- coding: utf-8 -*-
"""Name every product mark from what ALL FOUR editions know about it, not just one.

A set icon is the same drawing in every language. tools/iconsets.py groups the 288 traced
marks into 87 by shape, and that grouping is language-independent by construction — so
"which product is this?" has ONE answer, shared by all four books. But the resolver learns
that answer separately inside each corpus, out of that book's own citations, and the books
are not equally generous: the English FAQ cites 473 cards where the German cites 372, and
the Italian book votes on 20 marks where the English votes on 41. The result was a mark the
English edition names confidently and the German edition leaves as a bare "product icon" —
the same drawing, on the same page, unnamed only because the German book happens to cite
fewer cards around it. A screen reader then reads out "product icon" and the reader learns
nothing, in exactly the two languages that can least afford it.

So the votes are pooled: every corpus's pass-1 evidence into one urn per mark, the SAME
thresholds applied to it, and each language then writes the winner's name in its own words
from its own ArkhamDB index. Measured on the four current packs, the pooled answer agrees
with every confident per-language answer — not one mark where a book's own >=2-vote, >=80%
verdict differs — so this only ever fills a blank and never argues with a book about its own
marks. The thresholds are deliberately left alone: relaxing them would name a mark whose
pooled tally is {cycle 9: 18, cycle 10: 6}, stamping one product on 67 references a quarter
of whose evidence says the other.

Deliberately narrow: it sets `pn` on marks that have none, and nothing else. Card links are
NOT re-resolved from the pooled evidence — a link is a claim about one printing, and should
keep answering to the book that prints it.

Entry point: build(codes). Runs from ingest once every pack is written. It reads all four
data files whatever it is handed, because a name must never depend on which languages a
particular run happened to rebuild — otherwise `python tools/ingest.py de` would silently
strip German of every borrowed name.
"""
import json
import os
import sys

import adb
import adb_resolve
import iconsets
import langpack


PRODUCTS_DIR = os.path.join(langpack.ROOT, 'assets', 'products')

# The chapters that are a PRODUCT legend: the FAQ's closing icon tables and the Grimoire's
# icon-reference chapter. Keyed by the language-neutral section key, because every book titles
# and ids them differently. An ENCOUNTER-set table is deliberately not here: an encounter set is
# not a product, and naming a mark after one would be a category error however alike they look.
LEGEND_KEYS = ('faq-icons', 'icon-reference')


def _legend_rows(docs):
    """{art id: {language: row}} over every product legend in every book."""
    rows = {}
    for code, _path, data in docs:
        for s in data.get('sections') or []:
            if s.get('key') not in LEGEND_KEYS:
                continue
            for g in s.get('groups') or []:
                for it in g.get('items') or []:
                    if it.get('art'):
                        rows.setdefault(it['art'], {})[code] = it
    return rows


def _legend_name(row, idx):
    """What a legend row calls its product, in this book's own language."""
    pack = row.get('pack')
    return (idx.pack_name(pack) if pack else '') or (row.get('name') or '').strip()


def from_legend(docs, idxs, grp, quiet=False):
    """Name each mark from the row the books' own icon legend prints beside that very drawing.

    The votes pooled in build() are inference — the mark is opaque, so what it means is deduced
    from the cards cited around it. The legend is not inference: it is the book stating, in
    print, that THIS drawing is THAT product. It had simply never been consulted, because the
    prose traces and the legend's traces live in different directories and nothing compared
    them (see iconsets.same_picture).

    ATOMIC PER GROUP, and AUTHORITATIVE. Filling only the blanks looks safe and is not: group
    e1-e9ec28f9 is blank in German and Italian but already named in English and Spanish, so
    blanks-only would leave one drawing calling itself two different products in a single
    build — the exact thing this module exists to prevent. So a group takes the legend's answer
    in every book at once, over whatever the votes had concluded.

    The legend outranks the votes because the votes are demonstrably wrong where the two
    disagree, and wrong in a way that shows: before this, sixteen product names were attached
    to MORE THAN ONE distinct drawing — "Return to the Night of the Zealot" sat on four
    different marks, "Nathaniel Cho" on four — which cannot be, and is the signature of an
    under-attested tally settling on whichever product it saw first. The legend tells the four
    Returns apart because the book prints each one beside its own name.

    Every override is reported, so a disagreement between the two sources is visible rather
    than silently resolved."""
    pool = iconsets.bitmaps(PRODUCTS_DIR)
    traces = iconsets.bitmaps(iconsets.FAQSETS_DIR)
    rows = _legend_rows(docs)

    # Which drawing each shape group is, and what every book already calls it.
    art_of, named_as = {}, {}
    for code, _path, data in docs:
        for runs in adb_resolve.walk(data['sections']):
            for r in runs:
                if r.get('kind') != 'seticon':
                    continue
                gid = grp.get(r.get('fp'), r.get('fp'))
                if gid not in art_of:
                    bits = traces.get(r.get('fp'))
                    art = iconsets.same_picture(bits, pool) if bits else None
                    art_of[gid] = art if art in rows else None
                if r.get('pn'):
                    named_as.setdefault(gid, {}).setdefault(code, r['pn'])

    filled, fixed, touched, overrides = {}, {}, set(), []
    for gid, art in sorted(art_of.items()):
        if not art:
            continue
        want = {c: _legend_name(rows[art][c], idxs[c]) for c in rows[art] if c in idxs}
        want = {c: v for c, v in want.items() if v}
        if not want:
            continue
        clash = sorted({c for c, pn in (named_as.get(gid) or {}).items()
                        if c in want and pn != want[c]})
        if clash:
            overrides.append((gid, art, clash, named_as[gid][clash[0]], want[clash[0]]))
        for code, path, data in docs:
            if code not in want:
                continue
            for runs in adb_resolve.walk(data['sections']):
                for r in runs:
                    if r.get('kind') != 'seticon' \
                            or grp.get(r.get('fp'), r.get('fp')) != gid \
                            or r.get('pn') == want[code]:
                        continue
                    bucket = fixed if r.get('pn') else filled
                    bucket[code] = bucket.get(code, 0) + 1
                    r['pn'] = want[code]
                    touched.add(path)
    if not quiet:
        new = ', '.join(f'{c}+{filled[c]}' for c in sorted(filled)) or 'none'
        corr = ', '.join(f'{c}+{fixed[c]}' for c in sorted(fixed)) or 'none'
        print(f"  product marks named from the books' own icon legend: named {new}; "
              f'corrected {corr}')
        for gid, art, clash, was, now in overrides:
            print(f'  [note] mark {gid} is drawn in the legend as {art} ("{now}"); '
                  f'{"/".join(clash)} had inferred "{was}" from the cards cited around it '
                  f'— the printed legend wins.', file=sys.stderr)
    return filled, touched, overrides


def _paths(code):
    for what in ('grimoire', 'faq'):
        p = os.path.join(langpack.DATA_DIR, f'{what}_{code}.json')
        if os.path.exists(p):
            yield p


def build(codes=None, quiet=False):
    """Fill in the product name of every mark the pooled evidence identifies. -> report dict."""
    # Every language that HAS a corpus, whatever this run was asked to build — a mark's name
    # must not depend on which languages happened to be rebuilt. A ui-only language has no
    # corpus and no marks, so asking ArkhamDB about it would be a pointless fetch.
    codes = sorted({c for c in set(langpack.codes()) | set(codes or []) if any(_paths(c))})
    idxs = {c: adb.index(c) for c in codes}
    idxs = {c: i for c, i in idxs.items() if i is not None}
    if not idxs:
        return None
    grp = iconsets.groups()

    # Read every corpus BEFORE naming anything: the urn has to be complete, and the same for
    # all four, or a language would be named from a subset of the evidence.
    docs, pooled = [], {}
    for code, idx in idxs.items():
        for path in _paths(code):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            docs.append((code, path, data))
            for gid, tally in adb_resolve.vote(data['sections'], idx, grp).items():
                for cyc, n in tally.items():
                    pooled.setdefault(gid, {}).setdefault(cyc, 0)
                    pooled[gid][cyc] += n
    # Quiet: a mark several campaigns claim has already been reported once per corpus by the
    # resolver itself, and repeating it here would say nothing new.
    learned = adb_resolve.learn(pooled, quiet=True)

    # The books' own legend first: it STATES what a drawing is, where the votes only infer it.
    legend_filled, legend_touched, _clashes = from_legend(docs, idxs, grp, quiet)

    filled = {}
    for code, path, data in docs:
        idx, n = idxs[code], 0
        for runs in adb_resolve.walk(data['sections']):
            for r in runs:
                if r.get('kind') != 'seticon' or r.get('pn'):
                    continue          # never argue with a name this book's own evidence produced
                got = learned.get(grp.get(r.get('fp'), r.get('fp')))
                if not adb_resolve.confident(got):
                    continue
                pn = idx.campaign_name(got[0])
                if pn:
                    r['pn'] = pn
                    n += 1
        if n or path in legend_touched:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            filled[code] = filled.get(code, 0) + n

    if not quiet:
        detail = ', '.join(f'{c}+{filled[c]}' for c in sorted(filled)) or 'nothing to fill'
        print(f'  product marks named from all editions: {len(learned)} mark(s) identified '
              f'pooled ({detail})')
    return {'marks': len(learned), 'filled': filled}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build(sys.argv[1:] or None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
