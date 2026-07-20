# -*- coding: utf-8 -*-
"""Upgrade each "Name ( 20)" card reference from an ArkhamDB *search* to the exact card.

The books identify a card the way the card does: a name, the product's icon, and the card's
collection number. Until now the site linked the name to a search, because the number alone is
ambiguous — position 1 is Daniela Reyes in the 2026 Core Set, Tommy Muldoon in his own deck, and
someone else again in every older product. But the page prints the product's icon right there
between the parenthesis and the number, and the parser now recovers it (faq_seticons for the FAQ,
grim_vecicons for the Grimoire). Name + number + icon is enough to name the card exactly.

It is resolved in two passes, so nothing has to be hand-mapped and every answer is checkable:

  1. **Name and number.** Ask ArkhamDB which cards are printed at that position under that name.
     One answer is the card. Each such hit also *teaches* which product the reference's icon
     stands for — the icon is opaque vector art, but the cards it sits beside are not.
  2. **The icon.** Anything still ambiguous ("Daniela Reyes ( 1)" — the 2026 Core Set and Edge of
     the Earth both print a Daniela Reyes at position 1) is settled by the icon's product, and a
     reference whose name ArkhamDB spells differently in this language is resolved by product and
     position alone — but only for an icon that several unambiguous references agree on.

Whatever is left keeps its search link: an honest fallback is better than a confident wrong card.
Because the icon's product is learned rather than declared, it also gives every set icon a real
accessible name ("Core Set (2026)") instead of a generic "product icon".

Entry point: resolve(sections, code). Run it after cardlinks/link_cards, once the references are
`adbcard` runs. `python tools/adb_resolve.py <lang>` re-runs it over the built data and reports.
"""
import json
import os
import re
import sys

import adb
import iconsets
import langpack

_NUMS = re.compile(r'^\s*\(\s*(\d+[a-z]?(?:\s*,\s*\d+[a-z]?)*)\s*\)')
_MIN_VOTES = 2                 # an icon must be taught by this many unambiguous references…
_MIN_SHARE = 0.8               # …and they must agree this strongly, before it resolves alone


def _refs(runs):
    """Every card reference in a run list, as (adbcard_run, number, [icon runs]).

    A reference is an `adbcard` run followed by the "( <icon> 20)" the linker left as text —
    possibly broken into several runs by the set icon sitting inside the parenthesis."""
    out = []
    for i, r in enumerate(runs):
        if r.get('kind') != 'adbcard':
            continue
        # Scan until the closing bracket, bounded by how much TEXT has gone by rather than how
        # many runs: a reference naming two printings ("( 29, 5)") carries two icons, and each
        # one splits the text again, so it can take a dozen runs to cross a ten-character
        # bracket. Counting runs cut those references off half way and lost them entirely.
        buf, icons, j = '', [], i + 1
        while j < len(runs) and ')' not in buf and len(buf) <= 30:
            nxt = runs[j]
            if nxt.get('kind') == 'seticon':
                icons.append(nxt)
            elif nxt.get('kind') == 'text':
                buf += nxt.get('t', '')
            else:
                break
            j += 1
        m = _NUMS.match(buf)
        if not m:
            continue
        nums = re.findall(r'\d+', m.group(1))
        out.append((r, [int(n) for n in nums], icons))
    return out


def _walk(sections):
    for s in sections:
        for b in s.get('intro', []) or []:
            yield b.get('runs', [])
        for e in s.get('entries', []) or []:
            if e.get('titleRuns'):
                yield e['titleRuns']
            for b in e.get('blocks', []) or []:
                yield b.get('runs', [])
        ub = s.get('ub') or {}
        for bucket in ('ultimatums', 'boons', 'refractions'):
            for it in ub.get(bucket, []) or []:
                for b in it.get('blocks', []) or []:
                    yield b.get('runs', [])


def _learn(votes, quiet=False):
    """icon group -> (campaign, votes, share) for the icons the references agreed on.

    A group whose references disagree is reported rather than trusted: either the shape grouping
    merged two different marks, or a reference is mis-parsed. Both are worth seeing."""
    out = {}
    for gid, tally in votes.items():
        total = sum(tally.values())
        cyc, n = max(tally.items(), key=lambda kv: kv[1])
        out[gid] = (cyc, n, n / float(total))
        if not quiet and total >= 3 and n / float(total) < _MIN_SHARE:
            print(f'  [warn] set icon {gid} is claimed by several campaigns '
                  f'({", ".join(f"{c}x{k}" for c, k in sorted(tally.items(), key=lambda kv: -kv[1]))})'
                  f' — it resolves nothing on its own.', file=sys.stderr)
    return out


def _close(a, b):
    """Two card names near enough to be the same card: equal, or one contained at either end
    of the other.

    This is what keeps the by-position resolution honest. The reference's name and ArkhamDB's
    rarely differ, but when they do it is by a word at one end — the page abbreviates ("Henry
    Armitage" for "Dr. Henry Armitage", "Thompson" for ".45 Thompson"), or the parser swallowed
    the words before it ("Cada Progenie de Yog-Sothoth"). Two *different* cards never overlap
    that way, so "The Painted World" is refused a card ArkhamDB calls "Fieldwork"."""
    if not a or not b or len(min(a, b, key=len)) < 5:
        return False
    return (a == b or a.startswith(b) or b.startswith(a)
            or a.endswith(b) or b.endswith(a))


def resolve(sections, code, quiet=False):
    """Give every resolvable card reference its exact ArkhamDB card code. Returns a report."""
    idx = adb.index(code)
    if idx is None:
        return None
    refs = []
    for runs in _walk(sections):
        refs.extend(_refs(runs))
    # The same product mark is traced under several fingerprints; group them by shape so all of
    # a product's references teach the same icon (see tools/iconsets.py).
    grp = iconsets.groups()

    def gid_of(icons):
        fp = icons[0].get('fp') if icons else None
        return grp.get(fp, fp)

    # Pass 1 — name + number. An unambiguous hit also votes for what its icon means.
    votes, packvotes, pending = {}, {}, []
    for run, nums, icons in refs:
        name = run.get('q') or run.get('t') or ''
        if run.get('code') or not nums:
            continue                               # already answered by hand (tools/card_links.json)
        # "( 29, 5)" is usually ONE card the publisher printed twice, and the page names the
        # first printing first — so that is the one the link opens, rather than dropping the
        # reference for being ambiguous. Sometimes, though, the bracket belongs to two different
        # cards ("Dagón (…), Hidra (…) ( 330a, 331a)") and the name nearest it goes with the LAST
        # number, so every number is tried until one names this card.
        num = next((n for n in nums if idx.at(name, n)), nums[0])
        cands = idx.at(name, num)
        if len(cands) == 1:
            run['code'] = cands[0]['code']
            gid, cyc = gid_of(icons), cands[0]['cycle']
            if gid and cyc is not None:
                votes.setdefault(gid, {}).setdefault(cyc, 0)
                votes[gid][cyc] += 1
                packvotes.setdefault(gid, {}).setdefault(cands[0]['pack'], 0)
                packvotes[gid][cands[0]['pack']] += 1
        else:
            pending.append((run, num, icons, cands))
    learned = _learn(votes, quiet)

    # Pass 2 — the icon settles the rest.
    by_icon, by_pack, unresolved = 0, 0, 0
    for run, num, icons, cands in pending:
        got = learned.get(gid_of(icons))
        if not got:
            unresolved += 1
            continue
        cyc, n, share = got
        pv = packvotes.get(gid_of(icons), {})

        def _prefer(c, _pv=pv):
            # The front of a double-sided card is the page a reader wants: a plain code ("03068")
            # over a sided one, and side a ("07330a") over side b. Then the product this icon's
            # other references came from. Sorted ascending, so the code compares the right way.
            return (0 if c['code'].isdigit() else 1, -_pv.get(c['pack'], 0), c['code'])

        if cands:
            hits = [c for c in cands if c['cycle'] == cyc]
            # A campaign can print the same card twice — the Core Set and the Revised Core both
            # hold Machete at 20. Same name, same number, same campaign: it is one card reprinted,
            # so prefer the product this icon's other references came from, else the newest.
            if len(hits) > 1:
                hits = sorted(hits, key=_prefer)[:1]
            if len(hits) == 1:
                run['code'] = hits[0]['code']
                by_icon += 1
                continue
        elif n >= _MIN_VOTES and share >= _MIN_SHARE:
            # No name match in this language — ArkhamDB may spell it differently, or the parser
            # swallowed a word into the name ("Cada Progenie de Yog-Sothoth"). The campaign and
            # the position, which is exactly what the page prints, name the card instead. Only
            # when the campaign numbers that position once; a cycle whose packs each restart
            # their numbering can offer several, and then a search link is the honest answer.
            ref = adb.key(run.get('q') or run.get('t') or '')
            hits = [h for h in idx.in_cycle(cyc, num) if _close(ref, adb.key(h['name']))]
            if len({adb.key(h['name']) for h in hits}) == 1:
                hits = sorted(hits, key=_prefer)[:1]                # front before back side
            if len(hits) == 1:
                run['code'] = hits[0]['code']
                by_pack += 1
                continue
        unresolved += 1

    # The icons now have names: a set icon can say which product it is instead of "product icon".
    named = 0
    for runs in _walk(sections):
        for r in runs:
            if r.get('kind') != 'seticon':
                continue
            got = learned.get(grp.get(r.get('fp'), r.get('fp')))
            if got and got[1] >= _MIN_VOTES and got[2] >= _MIN_SHARE:
                pn = idx.campaign_name(got[0])
                if pn:
                    r['pn'] = pn
                    named += 1
    # …and so does the link, so the reader knows which printing they are about to open.
    for run, _nums, _icons in refs:
        rec = idx.by_code.get(run.get('code'))
        if rec:
            pn = idx.pack_name(rec['pack'])
            if pn:
                run['pn'] = pn

    total = len(refs)
    direct = sum(1 for r, _n, _i in refs if r.get('code'))
    report = {'refs': total, 'direct': direct, 'byname': direct - by_icon - by_pack,
              'byicon': by_icon, 'bypack': by_pack, 'unresolved': total - direct,
              'icons': len(learned), 'named': named}
    if not quiet:
        print(f'  arkhamdb {code}: {direct}/{total} card references linked to the exact card '
              f'({report["byname"]} by name+number, {by_icon} by product icon, {by_pack} by '
              f'position), {len(learned)} product icon(s) identified, {named} icon(s) named')
    return report


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for code in (sys.argv[1:] or langpack.codes()):
        for what in ('grimoire', 'faq'):
            p = os.path.join(langpack.DATA_DIR, f'{what}_{code}.json')
            if not os.path.exists(p):
                continue
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            print(f'{what} {code}:')
            resolve(data['sections'], code)
    return 0


if __name__ == '__main__':
    sys.exit(main())
