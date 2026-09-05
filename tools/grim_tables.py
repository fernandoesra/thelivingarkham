# -*- coding: utf-8 -*-
"""Lift the one run-on "table" FFG prints as prose into a real table block.

The Grimoire's Standalone Mode entry gives the deck-building
    experience -> additional random basic weaknesses
table as a single sentence ("0-9 experience: 0 ... 10-19 experience: 1 ..."), which
the PDF parser keeps as one run-on paragraph — hard to read. This layer, run during
assemble.py (like grim_add / apply_ada), converts that run into a {type:'table'} block.

It is LANGUAGE-AGNOSTIC: the two column labels are read out of the text itself, so each
language keeps its own wording. It triggers ONLY on the exact five XP buckets
(0-9, 10-19, 20-29, 30-39, 40-49) in order, so it never fires on anything else, and it
is IDEMPOTENT — a block already turned into a table (or any block without those buckets)
is left untouched. Runs BEFORE the linkers so the surrounding prose still gets its
glossary auto-links; the table itself carries an empty `runs` so every downstream step
that reads b['runs'] keeps working.

Hooked in assemble.finalize; see tools/other/instructions.md.
"""
import re

_RANGE = re.compile(r'(\d{1,2})\s*[-–—]\s*(\d{1,2})')   # hyphen, en dash, em dash
_BUCKETS = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49)]


def _flat(runs):
    return ''.join(r.get('t', '') for r in (runs or []))


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _try_convert(text):
    """Return (before, [h1, h2], rows, after) if `text` carries the standalone XP table,
    else None. `rows` is a list of [range, count] strings; before/after are the prose that
    framed the run (either may be '')."""
    ms = list(_RANGE.finditer(text))
    if len(ms) < 5:
        return None
    # locate five consecutive matches equal to the XP buckets, in order
    start = None
    for i in range(len(ms) - 4):
        if all((int(w.group(1)), int(w.group(2))) == bk
               for w, bk in zip(ms[i:i + 5], _BUCKETS)):
            start = i
            break
    if start is None:
        return None
    m = ms[start:start + 5]
    before = text[:m[0].start()].strip()

    # row 0 spans up to row 1: "<XP label>: <count> <weakness label>"
    seg0 = text[m[0].end():m[1].start()]
    mm = re.match(r'\s*([^:]+?):\s*(\d+)\s+(.*)$', seg0, re.S)
    if not mm:
        return None
    xp_label = mm.group(1).strip()
    wk_label = mm.group(3).strip()          # count 0 -> plural form, our column header
    if not xp_label or not wk_label:
        return None

    rows = []
    for k in range(5):
        end = m[k + 1].start() if k < 4 else len(text)
        cm = re.match(r'\s*[^:]+?:\s*(\d+)', text[m[k].end():end])
        if not cm:
            return None
        printed = re.sub(r'\s+', '', text[m[k].start():m[k].end()])   # keep the printed dash
        rows.append([printed, cm.group(1)])

    # after = whatever follows the last row's weakness label
    seg_last = text[m[4].end():]
    lm = re.match(r'\s*[^:]+?:\s*\d+\s+', seg_last)
    tail = seg_last[lm.end():] if lm else seg_last
    if tail.startswith(wk_label):
        after = tail[len(wk_label):].strip()
    else:
        j = tail.find(wk_label)
        after = tail[j + len(wk_label):].strip() if j >= 0 else ''

    return before, [_cap(xp_label), _cap(wk_label)], rows, after


def apply(allsecs):
    """Convert every run-on standalone table found in `allsecs` in place. Returns the count."""
    n = 0
    for s in allsecs:
        for e in s.get('entries', []) or []:
            blocks = e.get('blocks') or []
            out, changed = [], False
            for b in blocks:
                if b.get('type') in ('p', 'bullet') and b.get('runs'):
                    conv = _try_convert(_flat(b['runs']))
                    if conv:
                        before, head, rows, after = conv
                        run0 = b['runs'][0]
                        if before:
                            rb = dict(run0); rb['t'] = before
                            nb = {'type': b['type'], 'runs': [rb]}
                            if b.get('level') is not None:
                                nb['level'] = b['level']
                            out.append(nb)
                        out.append({'type': 'table', 'head': head, 'rows': rows, 'runs': []})
                        if after:
                            ra = dict(run0); ra['t'] = after
                            out.append({'type': 'p', 'runs': [ra]})
                        changed = True
                        n += 1
                        continue
                out.append(b)
            if changed:
                e['blocks'] = out
    return n
