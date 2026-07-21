# -*- coding: utf-8 -*-
"""The ArkhamDB card index — what turns a printed "Name ( 20)" into a DIRECT card link.

The books name a card the way the card itself does: a name and its **collection number**, the
position the card holds inside its product. That pair is not a card id: ArkhamDB's ids are
per-product runs (Daniela Reyes is 12001 in the 2026 Core Set, Tommy Muldoon is 60151 in his
own investigator deck), and the same position repeats in every product ever printed. So the
only honest way to reach the exact card is to ask ArkhamDB which card sits at that position —
which is what this reads, once per build, from the public API (https://arkhamdb.com/api/doc):

  * /api/public/cards/?encounter=1   every card: code, name, pack_code, position — per language
  * /api/public/packs/               the product names — per language

`encounter=1` matters: without it the endpoint answers with player cards only, and the books
name encounter cards constantly (enemies, locations, treacheries), so two thirds of the
references would find nothing and silently keep a search link.

Card NAMES are per-language (es.arkhamdb.com serves Spanish names), and so is the link the
reader follows; the card CODE is the same everywhere. The answers are cached under
tools/other/_adb/ (git-ignored) so a rebuild does not re-download, and so a build with no
network still works from the last download. With neither cache nor network the index is simply
absent and every reference keeps its old search link — never a broken build.

Usage:  python tools/adb.py [<lang> ...] [--refresh]     (warms the cache, prints a summary)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

import langpack

CACHE_DIR = os.path.join(langpack.ROOT, 'tools', 'other', '_adb')
_UA = {'User-Agent': 'Mozilla/5.0 (TheLivingArkham build)'}
_PUNCT = re.compile(r'[^a-z0-9]+')


# A leading article, in every language the site ships. Needed for exactly two rows — the
# English book prints "Labyrinths of Lunacy" where ArkhamDB has "The Labyrinths of Lunacy",
# and the Italian "Gala di Mezzo Inverno" against "Il Gala di Mezzo Inverno" — and checked
# not to collide: all 114 pack names stay distinct in all four languages once stripped.
_ARTICLE = re.compile(r'^(?:the|la|le|el|los|las|il|lo|i|gli|l|der|die|das)\s+', re.I)
_TAIL_PAREN = re.compile(r'\s*\([^()]*\)\s*$')


def _pack_keys(name):
    """The keys a printed product name may match a pack under, best first.

    Tiered on purpose: the exact fold answers most rows, and the relaxations are only ever
    reached by a row the exact one missed, so a loosened rule can never steal a row that
    already had a confident answer."""
    name = (name or '').strip()
    if not name:
        return []
    out = []
    for cand in (name, _ARTICLE.sub('', name), _TAIL_PAREN.sub('', name),
                 _ARTICLE.sub('', _TAIL_PAREN.sub('', name))):
        k = key(cand)
        if k and k not in out:
            out.append(k)
    return out


def host(code):
    """ArkhamDB is per-language on subdomains; English is the bare domain (as the app links)."""
    return ('https://%s.arkhamdb.com' % code) if code and code != 'en' else 'https://arkhamdb.com'


def key(name):
    """Match key for a card name: folded, then stripped of every non-alphanumeric character.

    The books and ArkhamDB disagree on typography, not on names — curly vs straight apostrophes,
    a hyphen where the other has none, a trailing period. Folding all of that away matches
    "Grand-Mère's Charm" to "Grand-Mere s Charm" without ever matching two different cards."""
    return _PUNCT.sub('', langpack.fold(name or ''))


def _get(url):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def _cache_path(code, what):
    return os.path.join(CACHE_DIR, f'{what}_{code}.json')


def _fetch(code, what, refresh=False):
    """The API answer for one language, from the cache unless asked (or told) to download.

    Returns None when there is neither a download nor a cached copy — the caller then simply
    has no index, and the build carries on with search links."""
    path = _cache_path(code, what)
    if not refresh and os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            pass                                   # a truncated cache is worth re-downloading
    url = host(code) + '/api/public/%s/' % what + ('?encounter=1' if what == 'cards' else '')
    try:
        data = _get(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)                # offline: last download still answers
        print(f'  [warn] ArkhamDB {what} for {code!r} unavailable ({type(e).__name__}); '
              f'card references keep their search links.', file=sys.stderr)
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data


class Index(object):
    """Everything the resolver asks: which card is at a position, and in which products."""

    def __init__(self, code, cards, packs):
        self.code = code
        self.packs = {p['code']: p.get('name', p['code']) for p in packs}
        # …and the way back: the product name a book prints -> the pack code. ArkhamDB gives
        # every language the SAME 114 codes and translates only the names, which makes the
        # code the one identity a product has in all four books — what lets the icon tables
        # share a drawing per product instead of tracing one per language.
        self.by_packname = {}
        for p in packs:
            for k in _pack_keys(p.get('name', '')):
                self.by_packname.setdefault(k, p['code'])
        # The icon a book prints beside a card number is the CAMPAIGN's, and a campaign is
        # several products (a deluxe box and its mythos packs, or one big campaign expansion).
        # ArkhamDB calls that a cycle, so the cycle — not the pack — is what an icon identifies.
        self.cycle_of = {p['code']: p.get('cycle_position') for p in packs}
        self.cycle_name = {}
        for p in packs:
            cyc = p.get('cycle_position')
            if cyc is not None and (p.get('position') or 99) <= 1:
                self.cycle_name.setdefault(cyc, p.get('name', ''))
        # A campaign whose first product does not call itself first still has a name when it is
        # the ONLY product in its cycle: the 2026 Core Set sits at position 3 of a cycle holding
        # nothing else, so 33 marks across the four books were identified perfectly and still
        # read out as a bare "product icon". A one-product cycle cannot be mislabelled by its own
        # product; a cycle with several — the nine-strong promo and novella bucket — correctly
        # stays unnamed rather than lending one member's title to all of them.
        percycle = {}
        for p in packs:
            if p.get('cycle_position') is not None:
                percycle.setdefault(p['cycle_position'], []).append(p)
        for cyc, ps in percycle.items():
            if cyc not in self.cycle_name and len(ps) == 1:
                self.cycle_name[cyc] = ps[0].get('name', '')
        self.by_name_pos = {}                      # (namekey, position) -> [card, …]
        self.by_cycle_pos = {}                     # (cycle, position) -> [card, …]
        self.by_cycle = {}                         # cycle -> [card, …]
        self.by_code = {}                          # card code -> card
        for c in cards:
            pos, pack = c.get('position'), c.get('pack_code')
            if pos is None or not pack:
                continue
            rec = {'code': c.get('code'), 'name': c.get('name', ''), 'pack': pack, 'pos': pos,
                   'cycle': self.cycle_of.get(pack)}
            self.by_name_pos.setdefault((key(rec['name']), pos), []).append(rec)
            # Cards whose title has two parts — "Strange Solution (Restorative Concoction)",
            # "Archaic Glyphs (Guiding Stones)" — are one name and one subname on ArkhamDB, and
            # the books print them joined. Indexed both ways so either spelling finds the card.
            sub = c.get('subname')
            if sub:
                self.by_name_pos.setdefault((key(rec['name'] + ' ' + sub), pos), []).append(rec)
            # An act or agenda is one card with two faces, and the faces have DIFFERENT names:
            # 02277 is "The Path to the Hill" on the front and "A Sacrifice Made" on the back.
            # The books cite whichever face they mean ("Act 1b—A Sacrifice Made"), so the back
            # name has to find the card too — it is the same page on ArkhamDB either way.
            back = c.get('back_name')
            if back:
                self.by_name_pos.setdefault((key(back), pos), []).append(rec)
            self.by_cycle_pos.setdefault((rec['cycle'], pos), []).append(rec)
            self.by_cycle.setdefault(rec['cycle'], []).append(rec)
            self.by_code[rec['code']] = rec

    def at(self, name, pos):
        """Every card printed at `pos` under `name` — usually one, sometimes a reprint pair."""
        return self.by_name_pos.get((key(name), pos), [])

    def in_cycle(self, cycle, pos):
        """Every card at `pos` in that campaign — one, unless its products number separately."""
        return self.by_cycle_pos.get((cycle, pos), [])

    def by_cycle_all(self, cycle):
        """Every card in a campaign, wherever it sits — for a reference whose printed number
        names nothing, where only the name is left to go on."""
        return self.by_cycle.get(cycle, [])

    def pack_name(self, pack):
        return self.packs.get(pack, '')

    def pack_code(self, name):
        """-> the pack code a printed product name means, or '' if ArkhamDB has no such
        product. A miss is not a failure: the promo rows ("Novella", "Parallel") are
        CATEGORIES of promo, and ArkhamDB models no pack for them at all."""
        for k in _pack_keys(name):
            got = self.by_packname.get(k)
            if got:
                return got
        return ''

    def campaign_name(self, cycle):
        return self.cycle_name.get(cycle, '')

    def __len__(self):
        return len(self.by_code)


_CACHE = {}


def index(code, refresh=False):
    """The index for one language, built once per run. None if ArkhamDB cannot be reached."""
    if code in _CACHE and not refresh:
        return _CACHE[code]
    cards = _fetch(code, 'cards', refresh)
    packs = _fetch(code, 'packs', refresh) or []
    idx = Index(code, cards, packs) if cards else None
    _CACHE[code] = idx
    return idx


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    refresh = '--refresh' in sys.argv[1:]
    for code in (args or langpack.codes()):
        idx = index(code, refresh)
        if idx is None:
            print(f'{code}: no index (offline and no cache)')
            continue
        print(f'{code}: {len(idx)} cards in {len(idx.packs)} products '
              f'({"downloaded" if refresh else "cache or download"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
