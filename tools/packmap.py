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

    lines += ['', '', '## Products a book forgot to list', '',
              'Every product below exists in all four languages — ArkhamDB names it in each — but',
              'some editions leave it out of their icon table. That is a human omission, not a',
              'language exclusive, so the row can be completed from the shared record: the name',
              'from ArkhamDB in that language, and the icon we already hold.', '']
    miss = missing_products()
    if miss:
        lines += ['| Language | Missing | ArkhamDB name in that language | Listed by |',
                  '|---|---|---|---|']
        for code in sorted(miss):
            for pack, name, who in miss[code]:
                lines.append(f'| {code} | `{pack}` | {name} | {who} |')
    else:
        lines.append('Every book lists every product.')
    lines.append('')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    return total


DONORS = ('en', 'es', 'de', 'it')      # asked in this order, so the answer is not build-order


# Products NO edition prints, added from our own sourced icon and identity because they exist
# and every language's reader deserves them. This is the deliberate step past the books:
# complete() fills a gap one book left in a table another book has; add_extras() adds a product
# no book listed at all. Each carries an explicit name per language (so it needs no network and
# honours the Spanish title the owner uses), and an art id whose SVG is hand-placed in
# assets/products/ — write-once, so a rebuild never clobbers it (see faq_seticons.write_products).
#
#   film_fatale  — an ArkhamDB pack (cycle 70). ArkhamDB spells it "Film Fatale" in every
#                  language, but its Spanish release is "Rodaje Letal"; icon from the official
#                  print-and-play art.
#   meowlathotep — Barkham Horror's "The Meddling of Meowlathotep", a promo ArkhamDB models no
#                  pack for, so it can only be named here. No official German or Italian title
#                  exists, so those fall back to English, as the site does for untranslated
#                  content elsewhere. Icon traced from the community symbol sheet.
EXTRAS = [
    {'pack': 'film_fatale', 'art': 'film_fatale',
     'names': {'es': 'Rodaje Letal', 'en': 'Film Fatale', 'de': 'Film Fatale',
               'it': 'Film Fatale'}},
    {'pack': 'meowlathotep', 'art': 'meowlathotep',
     'names': {'es': 'La intromisión de Miaulathotep (Barkham)',
               'en': 'The Meddling of Meowlathotep', 'de': 'The Meddling of Meowlathotep',
               'it': 'The Meddling of Meowlathotep'}},
]

# The standalone group is found by an anchor pack it always contains, not by its heading, so it
# works whatever each edition titles it ("Standalone Product Icons" / "Iconos de productos
# independientes" / …).
_STANDALONE_ANCHOR = 'cotr'


def add_extras(datadir=None, quiet=False):
    """Add the products no edition prints (EXTRAS) to every language's standalone table. -> rows.

    Idempotent: a product already present (added before, or since printed) is left alone.
    Runs after complete(), so it sees the final, gap-filled tables."""
    import glob
    datadir = datadir or langpack.DATA_DIR
    added, report = 0, []
    for path in sorted(glob.glob(os.path.join(datadir, 'faq_*.json'))):
        code = os.path.basename(path)[len('faq_'):-len('.json')]
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        sec = next((s for s in data.get('sections', []) if s.get('kind') == 'icons'), None)
        if sec is None:
            continue
        grp = next((g for g in sec.get('groups', []) or []
                    if any(it.get('pack') == _STANDALONE_ANCHOR
                           for it in g.get('items', []) or [])), None)
        if grp is None:
            continue
        have = {it.get('pack') for it in grp.get('items', []) or []}
        mine = []
        for ex in EXTRAS:
            if ex['pack'] in have:
                continue
            name = ex['names'].get(code) or ex['names'].get('en')
            if not name:
                continue
            grp.setdefault('items', []).append(
                {'name': name, 'art': ex['art'], 'pack': ex['pack'], 'added': True})
            mine.append(ex['pack'])
            added += 1
        if mine:
            report.append(f'{code}+{len(mine)}')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    if not quiet:
        print(f'  extra products added (no edition prints them): {added} row(s)'
              + (f' ({", ".join(report)})' if report else ''))
    return added


def complete(datadir=None, quiet=False):
    """Add the products a book left out of its icon table. -> rows added.

    Every one of them exists in all four languages — ArkhamDB names it in each — so a book
    that omits one has simply forgotten it, and the reader of that language is the only one
    who cannot look the symbol up. The row is completed from what we already hold: the
    product's name in THAT language from ArkhamDB, and the shared drawing.

    Marked `added` so the page can say it is ours and not printed in this edition. We are
    not going to quietly put words in Asmodee's book.

    Runs after tools/artshare.py, so the drawing copied over is already the canonical one.
    Idempotent: a row that is already there (added before, or since printed) is left alone."""
    import glob
    datadir = datadir or langpack.DATA_DIR
    files, datas, tables = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(datadir, 'faq_*.json'))):
        code = os.path.basename(path)[len('faq_'):-len('.json')]
        with open(path, encoding='utf-8') as f:
            datas[code] = json.load(f)
        files[code] = path
        # (group index, item index, item) for every row that names a product
        rows = {}
        for s in datas[code].get('sections', []):
            if s.get('kind') != 'icons':
                continue
            for gi, g in enumerate(s.get('groups', []) or []):
                for ii, it in enumerate(g.get('items', []) or []):
                    if it.get('pack'):
                        rows.setdefault(it['pack'], (gi, ii, it))
        tables[code] = rows

    every = {}
    for code, rows in tables.items():
        for pack in rows:
            every.setdefault(pack, []).append(code)

    added, report = 0, []
    for code, rows in tables.items():
        idx = adb.index(code)
        if idx is None:
            continue                       # offline: nothing to name the product with
        sec = next((s for s in datas[code].get('sections', [])
                    if s.get('kind') == 'icons'), None)
        if sec is None:
            continue
        groups = sec.get('groups') or []
        mine = []
        for pack, who in sorted(every.items()):
            if pack in rows:
                continue
            donor = next((c for c in DONORS if c in who), who[0])
            gi, ii, src = tables[donor][pack]
            if gi >= len(groups):
                continue                   # this edition has no such table to add it to
            name = idx.pack_name(pack)
            if not name:
                continue                   # ArkhamDB cannot name it here; leave the gap visible
            item = {'name': name, 'art': src.get('art', ''), 'pack': pack, 'added': True}
            groups[gi].setdefault('items', []).insert(min(ii, len(groups[gi]['items'])), item)
            mine.append(name)
            added += 1
        if mine:
            report.append(f'{code}+{len(mine)}')

    for code, path in files.items():
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(datas[code], f, ensure_ascii=False)
    if not quiet:
        print(f'  icon tables completed: {added} product(s) a book had left out'
              + (f' ({", ".join(report)})' if report else ''))
    return added


def missing_products(datadir=None):
    """{language: [(pack, its name in that language, who does list it)]} — the products a
    book leaves out of its icon table but every other book (and ArkhamDB) knows about."""
    import glob
    datadir = datadir or langpack.DATA_DIR
    per = {}
    for path in sorted(glob.glob(os.path.join(datadir, 'faq_*.json'))):
        code = os.path.basename(path)[len('faq_'):-len('.json')]
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        rows = set()
        for s in data.get('sections', []):
            if s.get('kind') != 'icons':
                continue
            for g in s.get('groups', []) or []:
                for it in g.get('items', []) or []:
                    if it.get('pack'):
                        rows.add(it['pack'])
        per[code] = rows
    every = {}
    for code, rows in per.items():
        for pack in rows:
            every.setdefault(pack, set()).add(code)
    out = {}
    for code, rows in per.items():
        idx = adb.index(code)
        gaps = []
        for pack, who in sorted(every.items()):
            if pack in rows:
                continue
            gaps.append((pack, (idx.pack_name(pack) if idx else '') or '?',
                         ', '.join(sorted(who))))
        if gaps:
            out[code] = gaps
    return out
