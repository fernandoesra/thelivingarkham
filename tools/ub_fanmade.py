# -*- coding: utf-8 -*-
"""Add the fan-made "Cultist Challenges" Ultimatums & Refractions to the viewer.

FFG's Week of Arkham Horror 2026 event published a community "Cultist Challenges"
document: three general Ultimatums and, for the Children of Blood campaign, several
campaign-wide Ultimatums and scenario-specific Refractions. They are player-made, not
official FFG design, so each shows a bold centred credit on its card ("Created by X for
the Cultist Challenges…" — the app's ubfanmade/ubfanmadeanon UI strings, author as data).

These cards are NOT in the Grimoire's optional-rules chapter, so `ultimatums.attach`
cannot see them. Like `ub_cap1`'s FAQ chapter-1 refractions, this post-step injects them
straight into the Grimoire's `ub` buckets, pairing each with its card in the registry
(assets/ub/index.json; the art-less ones are frame-only placeholders flagged noart).

English is the native edition. Every other language gets these as pending via `ub_merge`
(exactly like a late English boon), so this ONLY injects for English and leaves the rest
to the cross-language fill — therefore it must run BEFORE ub_merge (and does, in both
ingest.py and the per-pack assemble.py hook).

The Children of Blood refractions are tagged chapter='cap2' (the 2026-era cut), so they show
in the viewer's Ch.2 filter beside the Grimoire's own Scorched Earth and under the campaign
filter. The `fanmade` marker is this step's own, so re-running is idempotent (drop fanmade,
re-add) and never collides with ub_cap1.

Source: tools/ub_fanmade.json. Usage:  python tools/ub_fanmade.py [<lang> ...]
"""
import json
import os
import sys

import langpack
import ultimatums

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ub_fanmade.json')
BUCKETS = ('ultimatums', 'boons', 'refractions')


def _grim_path(code):
    return os.path.join(langpack.DATA_DIR, f'grimoire_{code}.json')


def _ub_section(data):
    for s in data.get('sections', []):
        if s.get('kind') == 'ultimatums':
            return s
    return None


def _cards():
    with open(SRC, encoding='utf-8') as f:
        return json.load(f).get('cards', [])


def _bucket_of(cat, refraction):
    if refraction:
        return 'refractions'
    return 'boons' if cat == 'boon' else 'ultimatums'


def build(pack, quiet=False):
    # English is the native edition; the other languages are filled by ub_merge, so there
    # is nothing to inject here — and nothing to drop, since their copies are pending ones
    # ub_merge owns. (Dropping by the `fanmade` marker in a non-English pack would delete
    # exactly those merged copies.)
    if pack.code != 'en':
        return 0
    gpath = _grim_path(pack.code)
    if not os.path.exists(gpath):
        return 0
    gdata = json.load(open(gpath, encoding='utf-8'))
    sec = _ub_section(gdata)
    if sec is None or 'ub' not in sec:
        return 0
    ub = sec['ub']

    # Idempotent: drop anything a previous run of THIS step added, so a re-run rebuilds the
    # fan-made set fresh rather than appending duplicates. Match on the `fanmade` marker AND on
    # the source slug set — the marker is a SHARED field, so a grimoire already slimmed by
    # ub_registry has lost it, and dropping by marker alone would then duplicate every card.
    src_cards = _cards()
    fm_slugs = {c['slug'] for c in src_cards}
    for b in BUCKETS:
        if ub.get(b):
            ub[b] = [it for it in ub[b]
                     if not it.get('fanmade') and it.get('slug') not in fm_slugs]

    registry = ultimatums._registry()
    new_refr, missing = [], []
    added = 0
    for c in src_cards:
        slug = c['slug']
        card = registry.get(slug)
        if not card:
            missing.append(slug)
            continue
        refr = bool(c.get('refraction'))
        rec = {
            'slug': slug, 'name': c['name'], 'blocks': c.get('blocks', []),
            'cat': c['cat'], 'refraction': refr,
            'card': card['card'], 'w': card['w'], 'h': card['h'],
            'thumb': card['thumb'], 'tw': card['tw'], 'th': card['th'],
            'chapter': c.get('chapter', 'both'),
            'fanmade': True,
        }
        if c.get('author'):
            rec['author'] = c['author']
        if refr:
            campaign, scenario = c.get('campaign', ''), c.get('scenario', '')
            if campaign:
                rec['campaign'] = campaign
            if scenario:
                rec['scenario'] = scenario
            # The detail card only draws its campaign/scenario line when `subtitle` is
            # non-empty (ubDetailHTML); the explicit campaign/scenario fields above drive
            # the display and the filters, so this is just the line that trips that guard.
            sub = (f'{scenario} ({campaign})' if scenario and campaign
                   else campaign or scenario)
            if sub:
                rec['subtitle'] = [{'kind': 'text', 't': sub}]
            # Icons (encounter-set / campaign symbol) come from the registry if curated in
            # ub_refractions.json; absent for now (the Children of Blood art is pending).
            for k in ('set', 'collection'):
                if card.get(k):
                    rec[k] = card[k]
        if card.get('illus'):
            rec['illus'] = card['illus']
        if card.get('noart'):
            rec['noart'] = True
        if refr:
            new_refr.append(rec)
        else:
            ub.setdefault(_bucket_of(c['cat'], False), []).append(rec)
        added += 1

    # Ultimatums/boons sort in with the base cards by slug (as ultimatums.attach does). The
    # refractions are appended AFTER the existing ones so ub_cap1's cap2-first ordering of
    # the real refractions is left intact; ub_merge re-sorts English anyway, and the
    # post-merge ub_cap1 restores order — this only matters for a lone `assemble.py en`.
    for b in ('ultimatums', 'boons'):
        if ub.get(b):
            ub[b].sort(key=lambda it: ultimatums._slugify(it['name']))
    if new_refr:
        new_refr.sort(key=lambda it: ultimatums._slugify(it['name']))
        ub['refractions'] = ub.get('refractions', []) + new_refr

    with open(gpath, 'w', encoding='utf-8') as f:
        json.dump(gdata, f, ensure_ascii=False)
    if not quiet:
        msg = f'  ub fanmade {pack.code}: +{added} card(s)'
        if missing:
            msg += (f'  ({len(missing)} not in registry — import placeholders first: '
                    f'{", ".join(missing[:6])}{"…" if len(missing) > 6 else ""})')
        print(msg)
    return added


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
