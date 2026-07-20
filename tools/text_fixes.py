# -*- coding: utf-8 -*-
"""Apply the curated text corrections (tools/text_fixes.json) to the built data.

The parser is deliberately faithful: it copies the book's words, and it does not guess. That
leaves two kinds of blemish a content audit turns up, and this is where each is answered, once,
visibly, instead of being hidden inside the parser:

  * extraction — the PDF says the right thing but its text layer breaks it, typically a word split
    across a line break ("carta de Ju-\\ngador" -> "carta de Ju gador") or a hyphen lost at one;
  * source — the official PDF itself carries a typo ("el mazo de u jugador"). We correct it rather
    than teach it, and the rule records that we are knowingly diverging from the printed text.

Every rule must match at least once, or the build says so: a rule that stops matching means the
source was reprinted and the correction is now either wrong or unnecessary.

Also strips the icon font's private-use glyphs out of the PLAIN `title` strings. Those titles are
what the search index and every fallback read; the rich `titleRuns` carry the real icon runs, so
the glyph in the plain copy is a tofu box that only ever leaks into search.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXES = os.path.join(HERE, 'text_fixes.json')
_PUA = re.compile(r'[-]')


def _raw():
    if not os.path.exists(FIXES):
        return {}
    with open(FIXES, encoding='utf-8') as f:
        return json.load(f)


def load():
    """The per-language find/replace rules (the other keys are config, not rules)."""
    return {k: v for k, v in _raw().items()
            if not k.startswith('_') and k != 'dropDuplicateLead'}


def _dup_leads(lang):
    return (_raw().get('dropDuplicateLead') or {}).get(lang, [])


def _drop_dup_lead(blocks, words):
    """Drop a bold lead run that merely repeats the word starting the text after it.

    The parser folds a bold sub-heading into the paragraph beneath it, so the word renders
    twice ("Errata Errata will be added…"). Only fires when the repeat is real."""
    n = 0
    for b in blocks or []:
        runs = b.get('runs') or []
        if len(runs) < 2:
            continue
        first = runs[0]
        if first.get('kind') != 'text' or not first.get('bold'):
            continue
        w = (first.get('t') or '').strip()
        if w not in words:
            continue
        rest = ''.join(r.get('t', '') for r in runs[1:] if r.get('kind') == 'text').lstrip()
        if rest.startswith(w):
            b['runs'] = runs[1:]
            n += 1
    return n


def _strip_pua(s):
    """Drop private-use icon glyphs from a plain title and tidy the space they leave."""
    if not s or not _PUA.search(s):
        return s
    return re.sub(r'[ \t]{2,}', ' ', _PUA.sub('', s)).strip()


# Hits accumulate across calls: apply() runs once per CORPUS (the Grimoire, then the FAQ), and a
# correction naturally belongs to only one of them — so "matched nothing" is only meaningful once
# every corpus has been through. report_unused() is what says it, at the end of the build.
_SEEN = {}


def report_unused(quiet=False):
    """Warn about corrections that matched nothing anywhere — a stale rule, or a reprinted source."""
    seen_langs = {lang for (lang, _find) in _SEEN}      # only languages this build touched
    stale = [(lang, r['find']) for (lang, rules) in load().items() if lang in seen_langs
             for r in rules if not _SEEN.get((lang, r['find']))]
    if stale and not quiet:
        print(f'  [warn] {len(stale)} correction(s) in tools/text_fixes.json matched nothing — the '
              f'source may have been reprinted, so the fix is now wrong or unnecessary:', file=sys.stderr)
        for lang, find in stale:
            print(f'         {lang}: {find!r}', file=sys.stderr)
    return stale


def apply(sections, lang, quiet=False):
    """Rewrite text in place. Returns (replacements, pua_stripped)."""
    rules = load().get(lang, [])
    hits = [0] * len(rules)
    pua = [0]

    def fix(s):
        for i, r in enumerate(rules):
            if r['find'] in s:
                hits[i] += s.count(r['find'])
                s = s.replace(r['find'], r['replace'])
        return s

    def fix_runs(runs):
        for r in runs or []:
            if 't' in r and isinstance(r['t'], str):
                r['t'] = fix(r['t'])

    def fix_blocks(blocks):
        for b in blocks or []:
            fix_runs(b.get('runs'))

    def fix_title(e):
        if isinstance(e.get('title'), str):
            t = _strip_pua(e['title'])
            if t != e['title']:
                pua[0] += 1
            e['title'] = fix(t)

    words = _dup_leads(lang)
    dropped = [0]
    for s in sections:
        fix_title(s)
        fix_blocks(s.get('intro'))
        dropped[0] += _drop_dup_lead(s.get('intro'), words)
        for e in s.get('entries', []):
            fix_title(e)
            fix_runs(e.get('titleRuns'))
            fix_blocks(e.get('blocks'))
            dropped[0] += _drop_dup_lead(e.get('blocks'), words)
        # the ultimatums viewer keeps its cards beside the entries
        ub = s.get('ub') or {}
        for bucket in ('ultimatums', 'boons', 'refractions'):
            for it in ub.get(bucket, []):
                if isinstance(it.get('name'), str):
                    it['name'] = fix(it['name'])
                fix_runs(it.get('subtitle'))
                fix_blocks(it.get('blocks'))
        # icon tables and anatomy keys carry prose too
        for g in s.get('groups', []) or []:
            for it in g.get('items', []) or []:
                if isinstance(it.get('name'), str):
                    it['name'] = fix(it['name'])
        for k in s.get('keys', []) or []:
            for it in k.get('items', []) or []:
                fix_runs(it.get('desc'))

    for i, r in enumerate(rules):
        key = (lang, r['find'])
        _SEEN[key] = _SEEN.get(key, 0) + hits[i]
    total = sum(hits)
    if not quiet:
        print(f'  text fixes {lang}: {total} replacement(s)'
              + (f', {pua[0]} title(s) de-glyphed' if pua[0] else '')
              + (f', {dropped[0]} duplicated lead(s) dropped' if dropped[0] else ''))
    return total, pua[0]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for lang, rules in sorted(load().items()):
        print(f'{lang}: {len(rules)} correction(s)')
        for r in rules:
            print(f'  [{r.get("kind","?"):10}] {r["find"]!r} -> {r["replace"]!r}   ({r.get("note","")})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
