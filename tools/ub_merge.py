# -*- coding: utf-8 -*-
"""Fill the Ultimatums & Boons viewer across languages from English.

English is updated first, so it is the most complete edition. The viewer should
show the SAME cards in every language: a card a language has not translated yet
is shown in English, flagged with a banner and the version English added it in
(the changelog carries the rest). This reads each built grimoire_<lang>.json,
takes English's viewer items as the canonical set, and appends every missing one
to the other languages in place, tagged pending. Native items keep their order;
the pending ones follow, so "awaiting translation" reads as one group.

Idempotent — a pending item already present is skipped, so re-running is a no-op.
Run after every language is assembled (tools/ingest.py does this), or alone:

  python tools/ub_merge.py
"""
import glob, json, os, sys
import langpack
from ultimatums import _slugify

BUCKETS = ('ultimatums', 'boons', 'refractions')


def _ub(data):
    for s in data.get('sections', []):
        if s.get('kind') == 'ultimatums':
            return s
    return None


def _unlink(runs):
    """A copy of the runs with cross-reference links flattened to plain text (see merge)."""
    out = []
    for r in runs or []:
        if r.get('kind') in ('link', 'flowref'):
            out.append({'kind': 'text', 't': r.get('t', ''), 'bold': r.get('bold', False),
                        'italic': r.get('italic', False), 'ref': False})
        else:
            out.append(dict(r))
    return out


def merge(datadir=None, quiet=False):
    datadir = datadir or langpack.DATA_DIR
    paths = {}
    for p in glob.glob(os.path.join(datadir, 'grimoire_*.json')):
        code = os.path.basename(p)[len('grimoire_'):-len('.json')]
        paths[code] = p
    say = (lambda *_: None) if quiet else print
    if 'en' not in paths:
        say('  [ub_merge] no English data yet — cross-language fill skipped')
        return
    datas = {c: json.load(open(p, encoding='utf-8')) for c, p in paths.items()}
    en = _ub(datas['en'])
    if not en or 'ub' not in en:
        say('  [ub_merge] English has no ultimatums viewer — skipped')
        return
    canon = {b: en['ub'].get(b, []) for b in BUCKETS}

    reports = []
    for code, data in datas.items():
        sec = _ub(data)
        if not sec or 'ub' not in sec:
            continue
        ub = sec['ub']
        added = 0
        for b in BUCKETS:
            native = [it for it in ub.get(b, []) if not it.get('pending')]
            native.sort(key=lambda x: _slugify(x['name']))
            have = {it['slug'] for it in native}
            pend = []
            for it in canon[b]:
                if it['slug'] in have:
                    continue
                if code == 'en':
                    continue                      # English is the canon; nothing to fill
                p = {k: v for k, v in it.items() if k != 'since'}
                p['pending'] = True
                # The English text carries ENGLISH glossary ids ("glossary--deckbuilding"), which
                # do not exist in this language's corpus — its cross-references would point at
                # nothing. Copy the runs and flatten those links to plain text: the card still
                # reads in English, and no link dangles. They come back the day it is translated.
                if it.get('blocks'):
                    p['blocks'] = [{**b, 'runs': _unlink(b.get('runs'))} for b in it['blocks']]
                if it.get('subtitle'):
                    p['subtitle'] = _unlink(it['subtitle'])
                if it.get('since'):
                    p['sinceVer'] = it['since']
                pend.append(p)
                added += 1
            pend.sort(key=lambda x: _slugify(x['name']))
            ub[b] = native + pend            # native first, then the pending group
        if added:
            reports.append(f'{code}+{added}')

    for code, p in paths.items():
        json.dump(datas[code], open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    total = sum(len(canon[b]) for b in BUCKETS)
    say(f'  [ub_merge] canonical from en: {total} card(s); '
        f'filled {", ".join(reports) if reports else "nothing (all translated)"}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    merge()
