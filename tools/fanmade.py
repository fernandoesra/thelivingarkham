# -*- coding: utf-8 -*-
"""Attach the community's deeper skill-test timing reference to its Grimoire chapter.

The books give the skill test as one procedure with a diagram. The community has taken that
apart into every triggering point and named the cards that fire at each — a genuinely more
useful thing to have open mid-game, and something the official text does not attempt. It is
not official, though, so it is kept as a clearly-labelled second view of the chapter rather
than mixed into the book's own words (the site renders it behind a "official / fanmade"
switch, with the warning and the credit).

The source documents are pictures — a scanned Spanish PDF and an English PNG — so they were
transcribed by hand into tools/fanmade_skilltest.json, one block per language, each from its
own document. That file is the content; this only files it under the right chapter, matched by
the shared section key so it lands correctly in every language.

Entry point: attach(sections, code).
"""
import json
import os
import sys

import langpack

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, 'fanmade_skilltest.json')
SECTION_KEY = 'skill-tests'


def load():
    if not os.path.exists(SOURCE):
        return {}
    with open(SOURCE, encoding='utf-8') as f:
        return json.load(f)


FALLBACK = 'en'


def attach(sections, code, quiet=False):
    """Put this language's block on the skill-test chapter. Returns the number of rows.

    A language with no transcription of its own borrows the English one rather than showing
    nothing: the table is mostly card names and step numbers, and having it in the wrong
    language beats not having it at all. The borrowing is declared (`lang`), never hidden —
    the site tags the block so a screen reader switches voice, says plainly that it has not
    been translated, and asks for a translation."""
    data = load()
    block = data.get(code)
    origin = code
    if not block or not block.get('steps'):
        block, origin = data.get(FALLBACK), FALLBACK
    if not block or not block.get('steps'):
        return 0
    sec = next((s for s in sections if s.get('key') == SECTION_KEY), None)
    if sec is None:
        if not quiet:
            print(f'  [warn] fanmade timing: no {SECTION_KEY!r} chapter in {code}, not attached',
                  file=sys.stderr)
        return 0
    sec['fanmade'] = {
        'title': block.get('title', ''),
        'lead': block.get('lead', []),
        'steps': block['steps'],
        'credit': (data.get('credit') or {}).get(origin, {}),
        # The work all of these descend from, credited on every language's copy.
        'original': (data.get('credit') or {}).get('_original', {}),
    }
    if origin != code:
        sec['fanmade']['lang'] = origin
    if not quiet:
        borrowed = '' if origin == code else f' (in {origin}, not translated yet)'
        print(f'  fanmade timing {code}: {len(block["steps"])} row(s) attached to {sec["id"]}'
              f'{borrowed}')
    return len(block['steps'])


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    data = load()
    for code in sorted(k for k in data if not k.startswith('_') and k != 'credit'):
        b = data[code]
        print(f'{code}: {b.get("title","")!r} — {len(b.get("steps", []))} rows, '
              f'{len(b.get("lead", []))} lead paragraph(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
