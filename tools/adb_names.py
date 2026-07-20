# -*- coding: utf-8 -*-
"""Find the card references the typographic matcher cannot see, by asking ArkhamDB.

`cardlinks` recognises a reference by its *shape*: a run of Capitalised Words before a number
in brackets. That is how English titles are set, so it works there — and it quietly fails in
every language that titles cards in sentence case. Spanish prints "Mercado de los bajos fondos
( 77)": only the first word is capitalised, so the pattern stops at "Mercado", refuses it, and
the reference stays plain text. The Spanish FAQ prints 509 bracketed numbers and the shape
matcher linked 135 of them.

The number in the brackets is the card's position in its product, so there is a far better
question to ask than "does this look like a title?": *is there a card of this name at this
position?* This walks back word by word from each unlinked bracket and keeps the longest
answer ArkhamDB confirms — which needs no capitalisation rule, no per-language stop-word list,
and cannot invent a card that does not exist. "Double, Double ( 320)" is found whole because
the longer span is tried first; "the Machete ( 20)" links only "Machete", because that is the
card that is really there.

It runs *after* cardlinks, over what cardlinks left alone, so the established behaviour is
untouched and this only ever adds. Entry point: link(sections, code).
"""
import re
import sys

import adb

# A bracketed collection number: "( 20)", "(20)", "( 77a)". Multi-number references
# ("( 25, 26)") name two printings at once and are left to the search link.
# \x00 stands for a non-text run in the flattened text, and the set icon the books print
# between the bracket and the number is exactly that — so it has to be allowed inside.
# A reference can carry SEVERAL numbers ("( 29, 5)"): one card, printed in two products. The
# first is the one the page names first, and its icon is the first too, so that is the printing
# the link opens.
_BRACKET = re.compile(r'\([\s\x00]*(\d+)[a-z]?(?:[\s,\x00]*\d+[a-z]?)*[\s\x00]*\)')
# No punctuation stops the search backwards. It used to — a full stop, a bracket, a quote —
# and every one of those cut a real name in half: `Dr. Milan Christopher`, `“Let me handle
# this!”`, `Mr. “Rook”`, `Strange Solution (Restorative Concoction)`, `Barricade (level 3)`.
# The guard against nonsense spans is not punctuation; it is that ArkhamDB has to confirm a card
# of that name at that number, which no accidental span across a sentence boundary ever will.
_PAREN_TAIL = re.compile(r'\s*\([^()]*\)\s*$')
# A dash or slash inside a word ("Act 1b—A Sacrifice Made", "Subject 5U-21/“Suzi”") hides the
# name from a split on spaces, and both are stripped from the match key anyway, so they read as
# spaces here.
_DASHES = re.compile(r'[—–/]')
_POSSESSIVE = re.compile("['’]s$")
_TAIL_WORDS = 3        # how many words may stand between the name and its number
_MAX_WORDS = 9                            # the longest card names are well under this
_APOS = '’'


def _atoms(runs):
    """Flatten runs to (text, style) characters and opaque non-text atoms, keeping order.

    A card name can straddle several runs (an icon sits inside the brackets, an emphasis
    changes mid-name), so the search runs over the flat text and the runs are rebuilt after."""
    out = []
    for r in runs:
        if r.get('kind', 'text') == 'text' and isinstance(r.get('t'), str):
            style = {k: r.get(k, False) for k in ('bold', 'italic', 'ref', 'red')}
            for ch in r['t']:
                out.append(('c', ch, style))
        else:
            out.append(('o', r, None))
    return out


def _rebuild(atoms):
    """Atoms back to runs, re-merging adjacent characters that share a style."""
    out = []
    for kind, val, style in atoms:
        if kind == 'c':
            last = out[-1] if out else None
            if (last is not None and last.get('kind') == 'text'
                    and all(last.get(k, False) == style[k] for k in style)):
                last['t'] += val
            else:
                out.append(dict(kind='text', t=val, **style))
        else:
            out.append(val)
    return out


def _guarded(atoms, i):
    """True when the bracket at flat position `i` already belongs to a linked reference."""
    j = i - 1
    while j >= 0 and atoms[j][0] == 'c' and atoms[j][1] == ' ':
        j -= 1
    while j >= 0:
        if atoms[j][0] == 'o':
            if atoms[j][1].get('kind') == 'adbcard':
                return True
            if atoms[j][1].get('kind') == 'seticon':
                j -= 1                     # the set icon sits between the name and the number
                continue
        return False
    return False


def _link_runs(runs, idx, stats):
    atoms = _atoms(runs)
    text = ''.join(a[1] if a[0] == 'c' else '\x00' for a in atoms)
    spans = []                             # (start, end, name) of each name to wrap, left to right
    for m in _BRACKET.finditer(text):
        pos = int(m.group(1))
        if _guarded(atoms, m.start()):
            continue
        # The name ends just before the bracket; walk back over whole words, longest first.
        head = _DASHES.sub(' ', text[max(0, m.start() - 90):m.start()]).rstrip()
        if not head:
            continue
        # Words WITH their offsets, so the span can be cut out of the original text. Not found by
        # searching for the candidate: the page's own spacing is irregular ("Diario  onírico" has
        # two spaces), and a normalised candidate then matches nothing in the text it came from.
        words = [(w.group(0), w.start(), w.end()) for w in re.finditer(r'\S+', head)]
        base = max(0, m.start() - 90)
        best = query = span = None
        # The name does not always touch the bracket — the books write "Body of a Yithian *card*
        # ( 244)", "Corpse Dweller*'s* ( 259)" — so a few trailing words may stand between the
        # two. Tried nearest-first, so the closest reading wins and the link still wraps only the
        # name; then longest-first within that, so "Double, Double" beats "Double".
        for drop in range(_TAIL_WORDS + 1):
            tail = words[:len(words) - drop] if drop else words
            if not tail:
                break
            for k in range(min(_MAX_WORDS, len(tail)), 0, -1):
                part = tail[-k:]
                cand = ' '.join(w for w, _s, _e in part).lstrip(' ,;·—–-')
                if not cand:
                    continue
                # …the same phrase without its trailing parenthetical, and without an English
                # possessive. Some of those brackets are part of the title ("(Restorative
                # Concoction)" — ArkhamDB's subname, matched above) and some are the book saying
                # which copy it means ("(level 3)"), which is part of no card's name; and the
                # books write "Dagon's ( 330b)" as often as "Dagon ( 330a)". Trying each settles
                # it: the whole printed phrase is underlined, the bare name is what ArkhamDB is
                # asked about.
                for alt in (cand, _PAREN_TAIL.sub('', cand), _POSSESSIVE.sub('', cand)):
                    if alt and idx.at(alt, pos):
                        best, query = cand, alt
                        span = (base + part[0][1], base + part[-1][2])
                        break
                if best:
                    break
            if best:
                break
        if not best:
            continue
        spans.append((span[0], span[1], text[span[0]:span[1]], query))
    if not spans:
        return runs, 0
    out, prev = [], 0
    for start, end, name, query in spans:
        out.extend(atoms[prev:start])
        style = next((a[2] for a in atoms[start:end] if a[0] == 'c'), {})
        out.append(('o', {'kind': 'adbcard', 't': name, 'q': query,
                          'bold': bool(style.get('bold')), 'italic': bool(style.get('italic'))}, None))
        prev = end
    out.extend(atoms[prev:])
    stats[0] += len(spans)
    return _rebuild(out), len(spans)


def _walk(sections):
    """Every (holder, key) whose value is a run list — blocks, entry titles, viewer cards."""
    for s in sections:
        for b in s.get('intro', []) or []:
            yield b, 'runs'
        for e in s.get('entries', []) or []:
            if e.get('titleRuns'):
                yield e, 'titleRuns'
            for b in e.get('blocks', []) or []:
                yield b, 'runs'
        ub = s.get('ub') or {}
        for bucket in ('ultimatums', 'boons', 'refractions'):
            for it in ub.get(bucket, []) or []:
                for b in it.get('blocks', []) or []:
                    yield b, 'runs'


def link(sections, code, quiet=False):
    """Wrap every remaining "<name> ( 20)" whose card ArkhamDB confirms. Returns the count."""
    idx = adb.index(code)
    if idx is None:
        return 0
    stats = [0]
    for holder, key in _walk(sections):
        holder[key], _n = _link_runs(holder.get(key, []), idx, stats)
    if not quiet:
        print(f'  card names {code}: {stats[0]} further reference(s) found by name lookup')
    return stats[0]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
