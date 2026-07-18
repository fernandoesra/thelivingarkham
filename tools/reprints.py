# -*- coding: utf-8 -*-
"""Turn the "Modified Reprints" chapter's jumbled list into a clean table.

The book prints the reprints as a two-column list — card name, then a set symbol and
collection number in brackets. Read in reading order the columns interleave, and the
brackets split across lines differently in each language, so the raw parse is a mess
like  "Machete ("  "Guts ("  "20)"  "90)". This walks those tokens with a FIFO queue
(a name that opened a bracket waits for the next closing number), recovering the
(name, number) pairs in order — the same logic works for both editions.

Every card here is a reprint in the 2026 revised core set (grimoire icon AHC100,
ArkhamDB pack code 12), so each row also carries its ArkhamDB id (12 + the padded
number) for a language-aware link. Entry point: attach(sections, pack).
"""
import re

# The revised core set: its product icon (assets/products/…svg) and ArkhamDB pack code.
SET_ICON = 'AHC100'
ADB_PACK = '12'

_ORPHAN = re.compile(r'^\s*(\d+)\s*\)\s*$')              # a stray "20)" on its own line
_BULLET = re.compile(r'^(.*?)\s*\(\s*(\d+)?\s*\)?\s*$')  # "Name (" or "Name ( 20)"


def _text(block):
    return ''.join(r.get('t', '') for r in (block.get('runs') or []))


def attach(sections, pack):
    sec = next((s for s in sections if s.get('key') == 'reprints'), None)
    if sec is None:
        return None
    blocks = sec.get('intro') or []
    # The list begins at the first bullet shaped like a reprint entry — "Name (" or
    # "Name ( 20)", i.e. matching _BULLET. The prose bullets above it explain how
    # reprints work and, although they contain parentheses like "(la original...)",
    # never end on a bracket, so _BULLET rejects them. Everything before is the intro.
    start = next((i for i, b in enumerate(blocks)
                  if b.get('type') == 'bullet' and _BULLET.match(_text(b).strip())), None)
    if start is None:
        return None

    rows, queue = [], []
    for b in blocks[start:]:
        t = _text(b).strip()
        orphan = _ORPHAN.match(t)
        if b.get('type') == 'bullet':
            m = _BULLET.match(t)
            name = (m.group(1) if m else t).strip()
            num = m.group(2) if (m and m.group(2)) else None
            if num:
                rows.append((name, num))
            elif name:
                queue.append(name)
        elif orphan and queue:
            rows.append((queue.pop(0), orphan.group(1)))

    if not rows:
        return None
    sec['intro'] = blocks[:start]
    sec['reprints'] = [{'name': n, 'num': num, 'adb': ADB_PACK + num.zfill(3)}
                       for n, num in rows]
    sec['reprintsIcon'] = SET_ICON
    return {'reprints': len(rows)}
