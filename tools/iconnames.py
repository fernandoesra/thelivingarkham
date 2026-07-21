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


def _paths(code):
    for what in ('grimoire', 'faq'):
        p = os.path.join(langpack.DATA_DIR, f'{what}_{code}.json')
        if os.path.exists(p):
            yield p


def build(codes=None, quiet=False):
    """Fill in the product name of every mark the pooled evidence identifies. -> report dict."""
    codes = sorted(set(langpack.codes()) | set(codes or []))
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
        if n:
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
