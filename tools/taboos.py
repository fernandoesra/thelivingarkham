# -*- coding: utf-8 -*-
"""Build the interactive Taboo list (Resources) from ArkhamDB.

The retired FAQ prints the taboo list as prose (see the "La lista de tabúes" chapter). This
tool builds the *interactive* version the site shows under Resources: every card on the current
taboo list, grouped the way the book groups them — Chained/Unchained (an experience cost),
Mutated (a rules-text change) and Forbidden (barred) — each with a DIRECT link to the card on
ArkhamDB (in the reader's language), its collection number and product, and the mutation.

Everything is read from ArkhamDB's public API (https://arkhamdb.com/api/doc):
  * /api/public/taboos/            the taboo lists; the newest matches the newest FAQ
  * /api/public/cards/             every player card (name + pack + position), per language
  * /api/public/packs/             product names, per language
Card names, packs and the card links are per-language (es.arkhamdb.com, fr…); the mutation text
ArkhamDB stores is English only, so it is tagged lang="en" in the viewer. Absolutely every taboo
card exists in ArkhamDB, so this needs no fuzzy matching — the taboo list already names the codes.

The product ICON is matched best-effort to the FAQ's own product-icon table (built by
faq_seticons.extract_iconref), so a taboo card shows the same set symbol the rest of the site
uses; where a pack has no match there, the card simply shows its product name and number.

Run it when a new taboo list comes out (it writes data/taboos_<code>.json, committed like the
rest). Usage:  python tools/taboos.py [<lang> ...]
"""
import json
import os
import re
import sys
import urllib.request

import langpack

DATA_DIR = langpack.DATA_DIR
_UA = {'User-Agent': 'Mozilla/5.0 (TheLivingArkham build)'}


def _get(url):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _adb_host(code):
    """ArkhamDB is per-language on subdomains; English is the bare domain (as the app links)."""
    return ('https://%s.arkhamdb.com' % code) if code and code != 'en' else 'https://arkhamdb.com'


def newest_taboo():
    lists = _get('https://arkhamdb.com/api/public/taboos/')
    newest = sorted(lists, key=lambda x: x.get('date_start', ''))[-1]
    cards = newest['cards']
    if isinstance(cards, str):
        cards = json.loads(cards)
    return newest, cards


def _category(c):
    """The book's three buckets, in priority order: a barred card is Forbidden even if it also
    carries a note; a text change is Mutated; an experience cost alone is Chained/Unchained."""
    if c.get('deck_limit') == 0:
        return 'forbidden'
    if c.get('text'):
        return 'mutated'
    if 'xp' in c:
        return 'chained'
    return 'mutated'                       # a note with neither cost nor bar (rare) reads as a change


def _keynorm(s):
    """Alphanumeric-only fold, for matching an ArkhamDB pack name to a FAQ icon-table entry."""
    return re.sub(r'[^a-z0-9]+', '', langpack.fold(s or ''))


def _pack_icon_map(code):
    """pack-name (normalised) -> product SVG art id, read from THIS language's FAQ icon-reference
    (the campaign / standalone / starter / promo tables). Best-effort: a pack with no matching row
    just gets no icon. English names match ArkhamDB's English packs, so the English FAQ is used as
    a fallback source too — the art id is language-neutral."""
    out = {}
    for src in (code, 'en'):
        p = os.path.join(DATA_DIR, f'faq_{src}.json')
        if not os.path.exists(p):
            continue
        fdata = json.load(open(p, encoding='utf-8'))
        for s in fdata.get('sections', []):
            if s.get('kind') != 'icons':
                continue
            for g in s.get('groups', []):
                for it in g.get('items', []):
                    art = it.get('art')
                    if not art:
                        continue
                    name = it.get('name', '')
                    out.setdefault(_keynorm(name), art)
                    out.setdefault(_keynorm(re.sub(r'\s*\([^)]*\)\s*$', '', name)), art)
        break                              # this language's own FAQ wins; only fall through if absent
    return out


def build(code):
    newest, tcards = newest_taboo()
    host = _adb_host(code)
    cards = {c['code']: c for c in _get(host + '/api/public/cards/')}
    packs = {p['code']: p.get('name', p['code']) for p in _get(host + '/api/public/packs/')}
    icons = _pack_icon_map(code)

    order = {'chained': 0, 'mutated': 1, 'forbidden': 2}
    buckets = {'chained': [], 'mutated': [], 'forbidden': []}
    unresolved = []
    for tc in tcards:
        cd = cards.get(tc['code'])
        if not cd:
            unresolved.append(tc['code'])
            continue
        cat = _category(tc)
        rec = {
            'code': tc['code'],
            'name': cd.get('name', tc['code']),
            'pack': cd.get('pack_code', ''),
            'packName': packs.get(cd.get('pack_code', ''), ''),
            'position': cd.get('position'),
            'cat': cat,
        }
        art = icons.get(_keynorm(rec['packName']))
        if art:
            rec['art'] = art
        if 'xp' in tc:
            rec['xp'] = tc['xp']
        if tc.get('text'):
            rec['text'] = tc['text']
        if tc.get('exceptional'):
            rec['exceptional'] = True
        buckets[cat].append(rec)

    for b in buckets.values():
        b.sort(key=lambda r: (langpack.fold(r['name']), r.get('position') or 0))
    groups = [{'cat': c, 'cards': buckets[c]} for c in sorted(buckets, key=lambda c: order[c]) if buckets[c]]

    data = {
        'lang': code,
        'tabooId': newest.get('id'),
        'date': newest.get('date_start', ''),
        'source': host + '/rules#Taboo',
        'groups': groups,
        'counts': {c: len(buckets[c]) for c in buckets},
    }
    return data, unresolved


def data_path(code):
    return os.path.join(DATA_DIR, f'taboos_{code}.json')


def build_and_write(code, quiet=False):
    data, unresolved = build(code)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(data_path(code), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    if not quiet:
        n = sum(len(g['cards']) for g in data['groups'])
        withicon = sum(1 for g in data['groups'] for c in g['cards'] if c.get('art'))
        print(f'  taboos {code} -> data/taboos_{code}.json: taboo #{data["tabooId"]} ({data["date"]}), '
              f'{n} cards ({data["counts"]["chained"]} chained, {data["counts"]["mutated"]} mutated, '
              f'{data["counts"]["forbidden"]} forbidden), {withicon} with a product icon'
              + (f'; {len(unresolved)} not on ArkhamDB' if unresolved else ''))
    return data


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    codes = sys.argv[1:] or langpack.codes()
    for code in codes:
        try:
            build_and_write(code)
        except Exception as e:
            print(f'  [warn] taboos {code} skipped: {type(e).__name__}: {e}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
