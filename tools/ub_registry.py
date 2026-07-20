# -*- coding: utf-8 -*-
"""One record per card for the Ultimatums, Boons & Refractions viewer.

"Ultimatum of Scorched Earth" is one card. It has one picture, one illustrator, one
encounter-set symbol, one campaign symbol, and it belongs to one chapter — none of which
is a translation. Only its NAME and its RULE TEXT are.

Until now every language carried a whole copy of every card, and the copies drifted: the
Italian refraction for The Drowned City had no campaign symbol because the Italian FAQ's
own icon table does not list that campaign, and the German ones had none at all. Nobody
could see it, because a missing icon looks like a design decision.

So the shared half is lifted out into data/ub.json, written once:

    slug -> {cat, refraction, chapter, card, w, h, thumb, tw, th, illus, set, collection}

and each language keeps only what it actually says:

    {slug, name, subtitle, blocks, campaign, scenario, since, sinceVer, pending}

The app puts the two back together when it loads a language (hydrateUB in js/app.js), so
the viewer sees exactly the records it always did. Adding a language now means translating
names and rules; the pictures, the illustrators and the symbols come for free — and cannot
disagree, because there is only one of each.
"""
import json
import os
import collections

import langpack

# What belongs to the card rather than to a language. `set` and `collection` are art ids
# (the encounter-set and campaign symbols); `chapter` is which rulebook the card came from.
SHARED = ('cat', 'refraction', 'chapter', 'card', 'w', 'h', 'thumb', 'tw', 'th',
          'illus', 'set', 'collection')
BUCKETS = ('ultimatums', 'boons', 'refractions')

REGISTRY = os.path.join(langpack.DATA_DIR, 'ub.json')


def _grim_path(code):
    return os.path.join(langpack.DATA_DIR, 'grimoire_%s.json' % code)


def _ub_of(data):
    for s in data.get('sections', []):
        if s.get('kind') == 'ultimatums' and isinstance(s.get('ub'), dict):
            return s['ub']
    return None


def build(codes=None, quiet=False):
    """Write data/ub.json and slim every language's copy. -> (cards, fields lifted)."""
    def say(*a):
        if not quiet:
            print(*a)

    codes = list(codes or langpack.codes())
    loaded = {}
    for code in codes:
        path = _grim_path(code)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if _ub_of(data) is not None:
            loaded[code] = data
    if not loaded:
        say('  ub registry: no built language carries the viewer — skipped')
        return 0, 0

    # Gather every card, then agree on each shared field. Where the languages disagree it is
    # because some of them are MISSING a value, not because they mean different things — an
    # edition whose icon table omits a campaign simply had nothing to point at. The value the
    # most languages carry wins; ties go to the registry's own language order, so the answer
    # does not depend on the order the files happened to be read in.
    seen = collections.OrderedDict()
    for code in codes:
        ub = _ub_of(loaded.get(code) or {}) or {}
        for bucket in BUCKETS:
            for rec in ub.get(bucket, []):
                seen.setdefault(rec['slug'], []).append((code, rec))

    cards, lifted = {}, 0
    for slug, pairs in seen.items():
        shared = {}
        for key in SHARED:
            votes = collections.Counter()
            for code, rec in pairs:
                v = rec.get(key)
                if v not in (None, ''):
                    votes[json.dumps(v, ensure_ascii=False, sort_keys=True)] += 1
            if not votes:
                continue
            top = max(votes.values())
            best = [v for v, n in votes.items() if n == top]
            shared[key] = json.loads(best[0]) if len(best) == 1 else json.loads(
                next(json.dumps(rec.get(key), ensure_ascii=False, sort_keys=True)
                     for code, rec in pairs if rec.get(key) not in (None, '')))
        cards[slug] = shared

    with open(REGISTRY, 'w', encoding='utf-8') as f:
        json.dump({'cards': cards}, f, ensure_ascii=False)

    for code, data in loaded.items():
        ub = _ub_of(data)
        for bucket in BUCKETS:
            for rec in ub.get(bucket, []):
                for key in SHARED:
                    if key in rec:
                        del rec[key]
                        lifted += 1
        with open(_grim_path(code), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    filled = sum(1 for slug in cards
                 for key in ('set', 'collection')
                 if cards[slug].get(key)
                 and any(r.get(key) in (None, '') for _c, r in seen[slug]))
    say(f'  ub registry -> data/ub.json: {len(cards)} card(s) written once, '
        f'{lifted} duplicated field(s) removed from the languages'
        + (f'; {filled} symbol(s) a language was missing now come from the shared record'
           if filled else ''))
    return len(cards), lifted


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    build()


if __name__ == '__main__':
    main()
