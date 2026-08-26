# -*- coding: utf-8 -*-
"""Layer OFFICIAL campaign-guide additions onto the Grimoire as a new version.

FFG ships a keyword or rule in a campaign guide months before it folds that text into the Arkham
Grimoire. This lets The Living Arkham add it right away — clearly credited to the guide it came
from, not passed off as the official Grimoire — and drop it once the real Grimoire catches up.

Each language carries its own `langs/<code>/grim_add.json`:
    { version:{v,date,ed}, credit:{name,url}, additions:[{section, id, title, blocks:[...]}] }
`apply(allsecs, pack, versions, whatsnew)` inserts each addition as a real entry in its section
(the glossary for a keyword), stamps it `addedIn` = the new version, hangs a `source` credit on it,
appends the version to `versions` and its entries to `whatsnew`, and returns the credit (the build
puts it on `data['grimadd']` for the What's New banner). Called BEFORE the linkers so the added
text gets glossary auto-links exactly like the rest of the book. A language with no file is
untouched. Mirrors tools/faq.py `apply_ada` for the FAQ corpus.
"""
import json
import os
import re
import unicodedata

import langpack
from langpack import slugify

# The book alphabetises the way an index does: ignoring a leading article ("The Codex" files under
# C) and leading punctuation ('"For each"' files under F). Match that so a new keyword lands in the
# right slot; the glossary already prints A–Z, so we only INSERT, never re-sort.
_ARTICLE = re.compile(r'^(the|el|la|los|las|un|una|unos|unas|le|les|il|lo|gli|der|die|das)\b\s*', re.I)


def _sortkey(title):
    s = unicodedata.normalize('NFD', title or '').encode('ascii', 'ignore').decode().lower().strip()
    s = re.sub(r'^[^a-z0-9]+', '', s)   # leading quotes / punctuation
    return _ARTICLE.sub('', s)          # leading article


def _entry_title(e):
    if e.get('title'):
        return e['title']
    return ''.join(r.get('t', '') for r in e.get('titleRuns', []) if r.get('kind', 'text') == 'text')


def _insert(sec, entry):
    """Glossary entries are alphabetical, so a new keyword is slotted in by title; other sections
    keep the book's own order, so an entry there is just appended."""
    entries = sec.setdefault('entries', [])
    if sec.get('key') == 'glossary':
        k = _sortkey(entry['title'])
        for i, e in enumerate(entries):
            if _sortkey(_entry_title(e)) > k:
                entries.insert(i, entry)
                return
    entries.append(entry)


def _norm_runs(runs):
    """Give text runs the same bold/italic/ref flags the parsed book carries, so an added entry is
    indistinguishable in shape from a real one (non-text runs — links, icons — pass through)."""
    out = []
    for r in runs:
        if r.get('kind', 'text') == 'text':
            out.append({'kind': 'text', 't': r.get('t', ''),
                        'bold': bool(r.get('bold')), 'italic': bool(r.get('italic')),
                        'ref': bool(r.get('ref'))})
        else:
            out.append(r)
    return out


def _block(b):
    out = {'type': b.get('type', 'p'), 'runs': _norm_runs(b.get('runs', []))}
    if out['type'] == 'bullet':
        out['level'] = b.get('level', 1)
    return out


def apply(allsecs, pack, versions, whatsnew):
    p = os.path.join(langpack.ROOT, 'langs', pack.code, 'grim_add.json')
    if not os.path.exists(p):
        return None
    data = json.load(open(p, encoding='utf-8'))
    ver, credit = data['version'], data['credit']
    secs = {s.get('key'): s for s in allsecs}
    source = {'name': credit['name'], 'url': credit['url']}
    new_items = []
    for add in data.get('additions', []):
        sec = secs.get(add['section'])
        if not sec:
            print(f"  [warn] grim_add {pack.code}: section {add['section']!r} not found — skipped")
            continue
        # Derive the id the same way real entries do (section id + slugified title), so it matches
        # each language's own convention (glossary--… in EN, glosario--… in ES) and routes correctly.
        entry = {
            'title': add['title'],
            'blocks': [_block(b) for b in add.get('blocks', [])],
            'id': add.get('id') or (sec['id'] + '--' + slugify(add['title'])),
            'addedIn': ver['v'],
            'source': source,
        }
        _insert(sec, entry)   # slotted into the glossary's A-Z order (not re-sorted at render)
        new_items.append({'id': entry['id'], 'title': entry['title'],
                          'sid': sec['id'], 'sec': sec.get('title', ''), 'num': sec.get('num', '')})
    if not new_items:
        return None
    v = {'v': ver['v'], 'date': ver['date']}
    if ver.get('ed'):
        v['ed'] = ver['ed']
    versions.append(v)
    whatsnew[ver['v']] = {'new': new_items, 'updated': []}
    return {'version': ver, 'credit': credit, 'new': new_items}
