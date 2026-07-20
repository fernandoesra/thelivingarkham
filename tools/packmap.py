# -*- coding: utf-8 -*-
"""Which product each row of the icon-reference tables is — the same answer in every language.

The tables print a product's NAME, and the name is translated. The drawing beside it is not:
"The Drowned City", "Die versunkene Stadt" and "La Città Sommersa" are one product with one
symbol. Until a row could say WHICH product it is, each language traced its own copy, and 28
of 36 products ended up with different art in at least two books — two of them sharing one
drawing, which is worse than a duplicate: it is a wrong icon.

ArkhamDB gives every language the same 114 pack codes and translates only the names, so the
code is that identity, and tools/adb.py already downloads and caches the list. This module
asks it for each row, and answers by hand for the rows ArkhamDB genuinely cannot answer.

An unresolved row is not an error and does not lose its icon: it simply keeps the art its own
language traced, exactly as before. What it loses is the sharing — so `report()` writes the
list, and tools/other/icon-products-unmatched.md is where the hand answers get decided.
"""
import json
import os

import adb
import langpack

# Rows ArkhamDB has no pack for, or names it spells differently from the book. Keyed by the
# folded row name so one entry answers for whichever language prints it that way.
#
# The promo rows are the honest case: "Novella" and "Parallel" are CATEGORIES of promo card,
# not products, and ArkhamDB models no pack for either — so they are given ids of their own
# rather than being forced onto a pack that does not exist.
ALIASES = {
    # promos — categories, not packs. One id each, shared by all four books.
    'novella': 'promo-novella',
    'novela': 'promo-novella',
    'romanzo': 'promo-novella',
    'romanpromos': 'promo-novella',
    'parallel': 'promo-parallel',
    'paralelo': 'promo-parallel',
    'parallelo': 'promo-parallel',
    'paralleleermittlerprintplay': 'promo-parallel',
    # the German FAQ drops the "c" from Jacqueline Fine
    'jaquelinefine': 'jac',
    # the Italian FAQ calls the core set "Set Base"; ArkhamDB's Italian pack is "Scatola Base"
    'setbaselanottedellazelota': 'core',
    'setbase': 'core',
}


# A row an edition misprints as a copy of the row above it. Keyed by (language, folded name,
# which occurrence) -> (pack, the name it should read).
#
# The English FAQ lists two standalone products under ONE name: "The Blob That Ate Everything"
# appears twice, and the second is a different product, "The Blob That Ate Everything Else!"
# (they even carry different marks — a meteor, and a meteor inside a disc). The German edition
# gets it right ("Der Blob, der alles fraß" / "Der Blob, der alles ANDERE fraß"), which is how
# we know it is the English book that is wrong and not our reading of it. Nothing in the text
# tells the two rows apart, so position is the only thing left to key on — kept here, visible,
# rather than hidden in the parser.
MISPRINTED_ROWS = {
    ('en', 'theblobthatateeverything', 2): ('blbe', 'The Blob That Ate Everything Else!'),
}

# Filled in as each language builds; tools/ingest.py writes the report from it at the end.
MISSED = {}


def _alias(name):
    return ALIASES.get(adb.key(name), '')


def resolve(items, code, quiet=True):
    """Stamp each icon-table item with the product it names. -> (resolved, unresolved names).

    Offline-safe: with no ArkhamDB index the rows simply keep no `pack`, and every language
    goes on showing the art it traced, which is what it did before this existed."""
    idx = adb.index(code)
    got, missing = 0, []
    seen = {}
    for it in items:
        name = it.get('name') or ''
        k = adb.key(name)
        seen[k] = seen.get(k, 0) + 1
        fix = MISPRINTED_ROWS.get((code, k, seen[k]))
        if fix:
            it['pack'], it['name'] = fix[0], fix[1]
            got += 1
            continue
        pack = _alias(name) or (idx.pack_code(name) if idx else '')
        if pack:
            it['pack'] = pack
            got += 1
        else:
            missing.append(name)
    if not quiet:
        print(f'  packs {code}: {got}/{len(items)} icon rows identified')
    return got, missing


REPORT = os.path.join(langpack.ROOT, 'tools', 'other', 'icon-products-unmatched.md')


def report(rows, path=REPORT):
    """Write the rows no product could be found for, so they can be answered by hand.

    `rows` is {language: [name, …]}. Written even when empty, so the file is never a stale
    copy of a problem that has since been fixed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    total = sum(len(v) for v in rows.values())
    lines = [
        '# Icon-table rows with no product identity',
        '',
        'Each row of the FAQ\'s icon-reference tables is matched to an ArkhamDB pack code, so',
        'that the same product shows the same drawing in every language (see tools/packmap.py).',
        'These rows found no pack and no alias, so each language still shows its own traced art.',
        '',
        'To answer one, add its folded name to `ALIASES` in tools/packmap.py. Two kinds turn up:',
        '',
        '* **not a product** — the promo rows are categories ("Novella", "Parallel"), and',
        '  ArkhamDB models no pack for them. These get an id of their own, not a pack code.',
        '* **spelled differently** — the book and ArkhamDB disagree about the name. Worth',
        '  checking which one is right before deciding.',
        '',
        'A row here is NOT broken: it keeps its own language\'s icon. What it loses is sharing.',
        '',
        f'**{total} unmatched row(s).**',
        '',
    ]
    if total:
        lines += ['| Language | Row as the book prints it | Folded key for ALIASES |',
                  '|---|---|---|']
        for code in sorted(rows):
            for name in rows[code]:
                lines.append(f'| {code} | {name} | `{adb.key(name)}` |')
    else:
        lines.append('Nothing outstanding — every row resolved.')
    lines.append('')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    return total
