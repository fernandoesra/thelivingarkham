# -*- coding: utf-8 -*-
"""Build the Ultimatums & Boons viewer from the grimoire, dynamically.

The "Reglas opcionales" / "Optional Rules" chapter already lists every base
Ultimatum and Boon as a bold name followed by its rule. This reads those items
straight out of the assembled chapter — no second copy to keep in sync — and
pairs each with its card picture from the language-neutral registry that
tools/import_ub_cards.py wrote (assets/ub/index.json).

The pairing is by a slug taken from the English card name. English grimoire
names slugify to that slug directly, so English needs no map. Every other
language ships a small name->slug map (langs/<code>/ub.json), because its
translated names cannot be guessed from an English filename — the same
"adding a language is data only" rule the rest of the pack follows.

The Spanish grimoire is an older edition and lists fewer items than the
English one; each language therefore shows exactly what ITS book contains,
which is the honest dynamic result. Refractions are past-campaign cards, not in
this chapter, and are added later. A grimoire item with no card art (the
English "Boon of Nodens" has none) is reported and left out of the gallery,
never shown as a broken tile.

Entry point: attach(sections, pack) — mutates the kind=="ultimatums" section in
place and returns a small summary for the build log.
"""
import json, os, re, unicodedata
import langpack

REG_PATH = os.path.join(langpack.ROOT, 'assets', 'ub', 'index.json')
# version/diff bookkeeping the chapter carries but a card's rule text should not
_DROP = ('v', 'red', 'addedIn', 'changedIn', 'new')


def _slugify(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()


def _norm(name):
    return ' '.join((name or '').split())


def _registry():
    if not os.path.exists(REG_PATH):
        raise langpack.PackError(
            'the Ultimatums & Boons card registry is missing (assets/ub/index.json).\n'
            '  Import the art first:  python tools/import_ub_cards.py')
    return json.load(open(REG_PATH, encoding='utf-8'))['cards']


def _namemap(pack):
    p = os.path.join(langpack.ROOT, 'langs', pack.code, 'ub.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def _clean(runs):
    out = []
    for r in runs:
        out.append({k: v for k, v in r.items() if k not in _DROP})
    if out and out[0].get('kind') == 'text':
        out[0]['t'] = out[0].get('t', '').lstrip()
    return out


def _has_content(runs):
    return any((r.get('t', '').strip() or r.get('kind') == 'icon') for r in runs)


def _subtitle(blocks):
    """A refraction's first line is its encounter-set subtitle, set in italic; split it
    off the rule so the card can place it under the title. Returns (subtitle_runs, rule
    blocks) — subtitle None when the first block does not start italic (a base card)."""
    if not blocks:
        return None, blocks
    runs = blocks[0].get('runs') or []
    i, sub = 0, []
    while i < len(runs) and runs[i].get('italic'):
        sub.append(runs[i]); i += 1
    if not sub:
        return None, blocks
    rest = [dict(r) for r in runs[i:]]
    if rest and rest[0].get('kind') == 'text':
        rest[0]['t'] = rest[0].get('t', '').lstrip()
    out = []
    if _has_content(rest):
        out.append({'type': 'p', 'runs': rest})
    out.extend(blocks[1:])
    return sub, out


def _items(entry):
    """Each item is a <p> whose leading run(s) are bold (its name); the rest is the
    rule. A following block with no bold lead continues the current item. The name
    run's version stamp is the edition the item was ADDED in (a wholly-new item has
    it on every run) — kept as `since` so a language that lacks the item can say when
    English got it."""
    items, cur = [], None
    for b in entry.get('blocks', []):
        runs = b.get('runs') or []
        if b.get('type') == 'p' and runs and runs[0].get('bold'):
            i, name_runs = 0, []
            while i < len(runs) and runs[i].get('bold'):
                name_runs.append(runs[i]); i += 1
            rest = runs[i:]
            cur = {'name': _norm(''.join(r.get('t', '') for r in name_runs)),
                   'since': name_runs[0].get('v') if name_runs else None, 'blocks': []}
            if _has_content(rest):
                cur['blocks'].append({'type': 'p', 'runs': _clean(rest)})
            items.append(cur)
        elif cur is not None:
            cur['blocks'].append({'type': b.get('type', 'p'), 'runs': _clean(runs)})
    return items


def attach(sections, pack):
    targets = [s for s in sections if s.get('kind') == 'ultimatums']
    if not targets:
        return None
    registry = _registry()
    namemap = _namemap(pack)
    src = next((s for s in sections if s.get('key') == 'optional-rules'), None)
    if src is None:
        raise langpack.PackError(
            f'langs/{pack.code}/lang.json: a "kind": "ultimatums" section needs the '
            f'"optional-rules" chapter to read its items from, but no section has that key.')

    def resolve(name):
        if namemap is not None:              # non-English: only the curated map
            return namemap.get(_norm(name))
        return _slugify(name)                # English: the name IS the slug

    # The registry is the single source of truth for what the gallery shows. An item is
    # shown only if its card is in it — which is exactly why the Refractions belong to a
    # later phase: their art is not imported yet, so their items (Scorched Earth and the
    # rest, listed in this same chapter) resolve to nothing and drop out on their own.
    # When their art is imported they appear with no code change here.
    cats = {'ultimatum': [], 'boon': [], 'refraction': []}
    textonly = []
    for e in src.get('entries', []):
        found = []
        for it in _items(e):
            found.append((it, resolve(it['name'])))
        # A carded entry is one that yielded at least one card in the registry. Only inside
        # such an entry does a missing card mean something (the English "Boon of Nodens" has
        # a rule but no fan card); a prose entry yields no cards and is ignored. This is what
        # keeps the base and the Refractions lists apart with no per-language heading test:
        # a Refractions card is tagged refraction in the registry and routed by that below,
        # while base cards route by their class — so a run without the refraction art simply
        # leaves those items unresolved and the Refractions tab empty.
        if not any(sl in registry for _it, sl in found):
            continue
        for it, slug in found:
            card = registry.get(slug)
            if not card:
                if slug and slug.startswith(('ultimatum-of-', 'boon-of-')):
                    textonly.append(slug)
                continue
            refr = bool(card.get('refraction'))
            bucket = 'refraction' if refr else card['cat']
            rec = {
                'slug': slug, 'name': it['name'], 'blocks': it['blocks'],
                'cat': card['cat'], 'refraction': refr,
                'card': card['card'], 'w': card['w'], 'h': card['h'],
                'thumb': card['thumb'], 'tw': card['tw'], 'th': card['th'],
            }
            if refr:
                sub, rule_blocks = _subtitle(rec['blocks'])
                if sub:
                    rec['subtitle'] = sub
                    rec['blocks'] = rule_blocks
                for k in ('set', 'collection'):
                    if card.get(k):
                        rec[k] = card[k]
            if card.get('illus'):
                rec['illus'] = card['illus']
            if card.get('noart'):
                rec['noart'] = True
            if it.get('since'):
                rec['since'] = it['since']
            cats[bucket].append(rec)

    for cat in cats:
        cats[cat].sort(key=lambda it: _slugify(it['name']))
    if not any(cats.values()):
        # The chapter is there and the cards are there, but nothing paired up. For a
        # non-English pack that almost always means its name->slug map is missing or
        # wrong: fail loudly with the fix, rather than ship a viewer of empty tabs.
        hint = ('English names are matched to the cards automatically'
                if namemap is None else f'check langs/{pack.code}/ub.json — its keys must '
                f'be the exact bold item names from the "optional-rules" chapter')
        raise langpack.PackError(
            f'langs/{pack.code}/lang.json: the "ultimatums" viewer paired no card with any '
            f'grimoire item. Its chapter has items and the registry has {len(registry)} '
            f'card(s), so the two are not lining up ({hint}).')
    ub = {'ultimatums': cats['ultimatum'], 'boons': cats['boon'],
          'refractions': cats['refraction']}
    for tgt in targets:
        tgt['ub'] = ub
        tgt.pop('figures', None)
    return {'ultimatums': len(cats['ultimatum']), 'boons': len(cats['boon']),
            'refractions': len(cats['refraction']), 'textonly': textonly}
