# -*- coding: utf-8 -*-
"""The product icons the Grimoire draws *inside* its sentences — recovered and put back.

The Grimoire prints a product's mark as vector art dropped into a gap in the text, so a plain
text parse walks straight past it and the sentence loses its meaning:

    "The five investigator decks (Tommy Muldoon , Carolyn Fern , André Patel …)"
                                              ^ his deck's mark was here
    "Can Daniela Reyes ( 1) use her Sledgehammer ( 28)?"
                        ^ the 2026 Core Set's mark, which says *which* Daniela Reyes

Same trick as the FAQ (tools/faq_seticons.py) and traced by the same tracer, but recovered
differently. The FAQ patches the parser to inject the icons while it reads; the Grimoire's parse
is long-tuned and its coverage measured against the printed page, so nothing here touches it.
Instead the PDF is scanned separately for icons sitting in a text gap, each keyed by the words on
either side of it, and the icons are slotted into the finished blocks afterwards by matching
those words. A key is folded and whitespace-collapsed, so it survives de-hyphenation and the
parser's own tidying; an icon whose context is not found simply is not placed, and the build says
how many.

That also feeds the ArkhamDB resolver (tools/adb_resolve.py), which needs the mark to tell one
product's card 1 from another's.

Entry points: scan(pdf) -> (icons, svgs); attach(sections, icons) -> count.
"""
import os
import re
import sys

import fitz

import faq_seticons
import icon_reference as ir
import langpack

_PRE = 22                      # characters of context kept before an icon…
_POST = 12                     # …and after it
_WS = re.compile(r'\s+')


def _norm(s):
    """Fold, collapse whitespace, drop the icon font's private-use glyphs. The key must survive
    the parser's own tidying, so it compares words, not typography."""
    s = re.sub('[-]', '', s or '')
    return _WS.sub(' ', langpack.fold(s)).strip()


def _line_text_before(spans, i, want):
    """The `want` characters printed just before span `i` on the same line."""
    out, y = '', spans[i]['bbox'][1]
    j = i
    while j >= 0 and len(out) < want + 40:
        if abs(spans[j]['bbox'][1] - y) > 4:
            break
        out = spans[j]['text'] + out
        j -= 1
    return out


def scan(pdf, quiet=False):
    """Every inline product mark in the PDF, as {(before, after): fingerprint}, plus its art.

    An icon is a cluster of dark filled paths sitting in the gap between two text spans of the
    same line — which is exactly how these marks are set, and nothing else in the book is."""
    doc = fitz.open(pdf)
    icons, svgs = {}, {}
    for pno in range(doc.page_count):
        page = doc[pno]
        spans = faq_seticons._page_spans(page)
        for i in range(len(spans) - 1):
            s0, s1 = spans[i], spans[i + 1]
            if abs(s0['bbox'][1] - s1['bbox'][1]) > 4:
                continue
            gx0, gx1 = s0['bbox'][2], s1['bbox'][0]
            if not (3 <= gx1 - gx0 <= 30):
                continue
            box = faq_seticons._tight_box(page, gx0, gx1,
                                          min(s0['bbox'][1], s1['bbox'][1]),
                                          max(s0['bbox'][3], s1['bbox'][3]))
            if box is None:
                continue
            w, h = box[2] - box[0], box[3] - box[1]
            if not (3 <= w <= 20 and 3 <= h <= 20):
                continue                       # too small to be a mark, or too big to be inline
            svg = ir.icon_svg(page, box)
            fp = faq_seticons._fingerprint(svg)
            if not fp:
                continue
            before = _norm(_line_text_before(spans, i, _PRE))[-_PRE:]
            after = _norm(s1['text'])[:_POST]
            if not before or not after:
                continue
            svgs.setdefault(fp, svg)
            icons.setdefault((before, after), fp)
    if not quiet:
        print(f'  vector icons: {len(icons)} context(s), {len(svgs)} distinct mark(s)')
    return icons, svgs


def _atoms(runs):
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


def _normalised(atoms):
    """(folded whitespace-collapsed text, index of the atom each character came from)."""
    text, at = [], []
    for i, a in enumerate(atoms):
        if a[0] != 'c':
            continue
        ch = _norm(a[1])
        if not ch:                                     # whitespace or a dropped glyph
            if text and text[-1] != ' ':
                text.append(' ')
                at.append(i)
            continue
        text.append(ch)
        at.append(i)
    return ''.join(text), at


def _already(atoms, idx, fp):
    """True when this very mark is already sitting at this spot.

    The same mark can be scanned under two keys — the page's line break puts a different run of
    words in front of it each time ("andre patel" and "de desastreandre patel") — and the longer
    key never matches inside a block, so it falls through to the short-context retry and lands
    exactly where the first key already placed it. Nothing in the books prints two identical
    marks side by side, so touching one is proof this is that duplicate, not a second icon."""
    for step in (-1, 1):
        k = idx + (step if step < 0 else 0)
        while 0 <= k < len(atoms) and atoms[k][0] == 'c' and atoms[k][1] == ' ':
            k += step
        if 0 <= k < len(atoms) and atoms[k][0] == 'o':
            r = atoms[k][1]
            if r.get('kind') == 'seticon' and r.get('fp') == fp:
                return True
    return False


def _place(runs, items, placed):
    """Insert every icon whose context is found in this run list. Returns (runs, indices used)."""
    atoms = _atoms(runs)
    text, at = _normalised(atoms)
    if not text:
        return runs, set()
    cuts, used = [], set()                             # (atom index to insert before, fingerprint)
    for n, (before, after, fp) in enumerate(items):
        start = 0
        while True:
            k = text.find(before, start)
            if k < 0:
                break
            start = k + 1
            j = k + len(before)
            # The page prints a space span where the icon is drawn, and the parser keeps it, so
            # the two sides of a key are not adjacent in the built text: step over that space.
            j2 = j
            while j2 < len(text) and text[j2] == ' ':
                j2 += 1
            if not text.startswith(after, j2):
                continue
            # Inside a card reference the mark belongs right after the bracket, as the FAQ sets
            # it; after a product's name it belongs after the space, before the comma.
            slot = j if before.endswith('(') else j2
            if slot < len(at):
                if _already(atoms, at[slot], fp):
                    used.add(n)                    # an earlier pass put it there; not twice
                    continue
                cuts.append((at[slot], fp))
                used.add(n)
    if not cuts:
        return runs, set()
    # Two keys for the same mark can also land a space apart WITHIN one pass, where the check
    # above sees nothing yet because neither has been inserted. Same rule: identical marks with
    # only spaces between them are one mark.
    out, byidx, kept = [], {}, []
    for idx, fp in sorted(cuts):
        if any(kfp == fp and all(atoms[t][0] == 'c' and atoms[t][1] == ' '
                                 for t in range(min(idx, kidx), max(idx, kidx)))
               for kidx, kfp in kept):
            continue
        kept.append((idx, fp))
        byidx.setdefault(idx, fp)
    for i, a in enumerate(atoms):
        if i in byidx:
            out.append(('o', {'kind': 'seticon', 'fp': byidx[i]}, None))
            placed[0] += 1
        out.append(a)
    return _rebuild(out), used


def _walk(sections):
    for s in sections:
        for b in s.get('intro', []) or []:
            yield b, 'runs'
        for e in s.get('entries', []) or []:
            if e.get('titleRuns'):
                yield e, 'titleRuns'
            for b in e.get('blocks', []) or []:
                yield b, 'runs'


_SHORT = 10                    # characters of context kept for the retry below


def _duplicates(sections):
    """Places where the same mark ended up slotted in twice, side by side.

    Nothing in the books prints two identical marks together, so this can only be a placement
    bug — and it is invisible in a diff of the data. Checked on every build rather than trusted:
    the guards in _place are what should make it impossible, and a build that starts reporting
    these is telling us one of them stopped holding."""
    n = 0
    for holder, key in _walk(sections):
        prev = None
        for r in holder.get(key) or []:
            kind = r.get('kind')
            if kind == 'seticon':
                if prev == r.get('fp'):
                    n += 1
                prev = r.get('fp')
            elif not (kind == 'text' and not (r.get('t') or '').strip()):
                prev = None                        # a space between two marks still adjoins them
    return n


def attach(sections, icons, quiet=False):
    """Slot each scanned mark back into the built blocks. Returns how many were placed."""
    placed = [0]
    items = [(b, a, fp) for (b, a), fp in sorted(icons.items())]
    holders = list(_walk(sections))
    done = set()
    for holder, key in holders:
        holder[key], used = _place(holder.get(key, []), items, placed)
        done |= used
    # A context the parser reshaped at its left edge is retried on its last few words alone:
    # the Grimoire's questions are printed "Q: Can Daniela Reyes ( 1)…" and the "Q: " is the
    # parser's cue to start an entry, so it is gone from the text the key has to match.
    retry = [(b[-_SHORT:], a, fp) for i, (b, a, fp) in enumerate(items)
             if i not in done and len(b) > _SHORT]
    if retry:
        for holder, key in holders:
            holder[key], _u = _place(holder.get(key, []), retry, placed)
    dup = _duplicates(sections)
    if not quiet:
        print(f'  vector icons: {placed[0]} placed back into the text '
              f'({len(icons)} scanned, {len(items) - len(done)} retried on a shorter context)')
        if dup:
            print(f'  [warn] {dup} place(s) show the same product mark twice in a row — a mark '
                  f'was slotted in by two different context keys; see _already in '
                  f'tools/grim_vecicons.py', file=sys.stderr)
    return placed[0]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for path in sys.argv[1:]:
        print(os.path.basename(path))
        icons, svgs = scan(path)
        for (b, a), fp in sorted(icons.items()):
            print(f'   {fp:14} …{b!r} | {a!r}…')
    return 0


if __name__ == '__main__':
    sys.exit(main())
