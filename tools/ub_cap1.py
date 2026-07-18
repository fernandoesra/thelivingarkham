# -*- coding: utf-8 -*-
"""Add the FAQ chapter-1 refractions to the Ultimatums & Boons viewer.

The viewer lives in the Grimoire (chapter 2) and shows the ultimatums, boons and
refractions of the 2026 rules. The retired FAQ (chapter 1) shares the SAME ultimatums and
boons but has many MORE refractions — one per campaign, ten years of them. Their card art
(5argon's, imported by `import_ub_cards.py --refractions`) is already in the registry; their
rule text lives in the FAQ. This post-step reads the FAQ chapter-1 refractions, pairs each
with its card, tags it `chapter="cap1"`, and appends it to the Grimoire's `ub.refractions`.
Existing viewer items are tagged too: the shared ultimatums/boons as `"both"`, the Grimoire's
own refractions (Scorched Earth) as `"cap2"` — which is what the viewer's chapter filter reads.

Runs after both the Grimoire and the FAQ are built, and before `ub_merge` (cross-language fill).
Usage:  python tools/ub_cap1.py [<lang> ...]
"""
import json
import os
import sys

import langpack
import ultimatums


def _grim_path(code):
    return os.path.join(langpack.DATA_DIR, f'grimoire_{code}.json')


def _faq_path(code):
    return os.path.join(langpack.DATA_DIR, f'faq_{code}.json')


def _ub_section(data):
    for s in data.get('sections', []):
        if s.get('kind') == 'ultimatums':
            return s
    return None


def _faq_refractions_entry(faq):
    """The FAQ's 'Refracciones' entry (chapter-1 refractions), inside its optional-rules
    section. Matched by key/id so it works in either language."""
    for s in faq.get('sections', []):
        if s.get('key') == 'faq-optional' or s.get('id', '').startswith('c1-ultimatum'):
            for e in s.get('entries', []):
                eid = e.get('id', '')
                if eid.endswith('refracciones') or eid.endswith('refractions'):
                    return e
    return None


def build(pack, quiet=False):
    gpath, fpath = _grim_path(pack.code), _faq_path(pack.code)
    if not (os.path.exists(gpath) and os.path.exists(fpath)):
        return 0
    gdata = json.load(open(gpath, encoding='utf-8'))
    fdata = json.load(open(fpath, encoding='utf-8'))
    sec = _ub_section(gdata)
    if sec is None or 'ub' not in sec:
        return 0
    ub = sec['ub']

    # Idempotent: drop any chapter-1 refractions a previous run added, so re-running always
    # rebuilds them fresh (in the FAQ's own order) rather than appending duplicates.
    ub['refractions'] = [it for it in ub.get('refractions', []) if it.get('chapter') != 'cap1']

    # Tag what is already there: shared ultimatums/boons show under any chapter; the
    # Grimoire's own refractions are chapter 2. setdefault leaves any prior tag.
    for b in ('ultimatums', 'boons'):
        for it in ub.get(b, []):
            it.setdefault('chapter', 'both')
    for it in ub.get('refractions', []):
        it.setdefault('chapter', 'cap2')

    entry = _faq_refractions_entry(fdata)
    if entry is None:
        if not quiet:
            print(f'  [warn] {pack.code}: no FAQ chapter-1 refractions entry found — nothing added.')
        return 0

    registry = ultimatums._registry()
    namemap = ultimatums._namemap(pack)

    def resolve(name):
        if namemap is not None:
            return namemap.get(ultimatums._norm(name))
        return ultimatums._slugify(name)

    have = {it.get('slug') for it in ub.get('refractions', [])}
    added, unresolved = [], []
    for it in ultimatums._items(entry):
        slug = resolve(it['name'])
        card = registry.get(slug) if slug else None
        if not card or not card.get('refraction'):
            unresolved.append(it['name'])
            continue
        if slug in have:
            continue
        sub, blocks = ultimatums._subtitle(it['blocks'])
        rec = {
            'slug': slug, 'name': it['name'], 'blocks': blocks,
            'cat': card['cat'], 'refraction': True,
            'card': card['card'], 'w': card['w'], 'h': card['h'],
            'thumb': card['thumb'], 'tw': card['tw'], 'th': card['th'],
            'chapter': 'cap1',
        }
        if sub:
            rec['subtitle'] = sub
        for k in ('set', 'collection', 'illus'):
            if card.get(k):
                rec[k] = card[k]
        added.append(rec)
        have.add(slug)

    if added:
        # cap 2 refraction(s) first, then the chapter-1 set in the FAQ's own order — which is
        # campaign order (Dunwich, Carcosa, the Forgotten Age, …), the order players expect.
        ub['refractions'] = ub.get('refractions', []) + added
        ub['refractions'].sort(key=lambda r: r.get('chapter') != 'cap2')   # stable: keeps order
        with open(gpath, 'w', encoding='utf-8') as f:
            json.dump(gdata, f, ensure_ascii=False)
    if not quiet:
        msg = f'  ub cap1 {pack.code}: +{len(added)} chapter-1 refraction(s)'
        if unresolved:
            msg += f'  ({len(unresolved)} unresolved: {", ".join(unresolved[:4])}…)'
        print(msg)
    return len(added)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    packs, _errs = langpack.load_valid(sys.argv[1:] or None)
    for p in packs:
        try:
            build(p)
        except langpack.PackError as e:
            print(f'  ERROR {p.code}: {e}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
