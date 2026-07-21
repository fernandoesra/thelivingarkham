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
# The same bracket with the product NAMED inside it as well as marked — "(Grundspiel <icon>
# 73)" — which is how the German edition cites. Only tried when the reference actually
# carries an icon, so a bracket that is merely parenthetical ("(level 3)", "(2016 or 2021)")
# cannot be read as a citation: those carry no mark. Without this the resolver saw 15 German
# references where the linker had found 343, so almost no German set icon could learn which
# product it stands for — and the icon's name is what a screen reader reads out.
_NUMS_NAMED = re.compile(r'^\s*\(\s*[^()\d]{1,28}?\s*(\d+[a-z]?(?:\s*,\s*\d+[a-z]?)*)\s*\)')
# The Italian edition does not bracket its citations at all: it prints the mark and the
# collection number BEFORE the name, joined by a dash — "<icon> 263 - Strana Soluzione
# (Mistura Risanante)". Nothing to find ahead of the name, so those references resolved to a
# search link and the resolver saw 284 of 432; the other three editions were at 91-98%.
# Anchored at the end because the number sits immediately before the name it belongs to, and
# only ever tried when a mark is there too, so ordinary prose ("… pagina 3 - vedi") cannot be
# read as a citation.
_LEADNUM = re.compile(r'(\d+[a-z]?)\s*[-–—]\s*$')
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
        # 48, not 30: a bracket that names its product ("(Die Innsmouth-Verschwörung <icon>
        # 202)") is longer than one that only marks it. The scan still stops at the closing
        # bracket, so a wider bound only lets a longer real bracket through.
        while j < len(runs) and ')' not in buf and len(buf) <= 48:
            nxt = runs[j]
            if nxt.get('kind') == 'seticon':
                icons.append(nxt)
            elif nxt.get('kind') == 'text':
                buf += nxt.get('t', '')
            elif nxt.get('kind') == 'icon':
                # An inline game glyph printed INSIDE the bracket. The Spanish FAQ marks the
                # Core Set with the elder sign, which the icon stage reads as an ordinary glyph
                # rather than a set mark, so the scan stopped dead at it with buf=' (' and lost
                # the number as well — 36 Spanish references, the largest single cause there.
                # A glyph is not the end of a bracket; the ')' and the budget still are.
                pass
            else:
                break
            j += 1
        m = _NUMS.match(buf)
        if not m and icons:
            m = _NUMS_NAMED.match(buf)
        if not m:
            # Nothing ahead of the name — look BEHIND it for the Italian form (see _LEADNUM).
            lead = _lead_ref(runs, i)
            if lead:
                # The number comes from behind the name; the MARK still comes from in front of
                # it, because that is where this form prints it: "263 - Nome <icon>". Dropping
                # the icons the forward scan already collected left every lead-in reference
                # with no product at all — so it cast no vote for its own mark in pass 1, and
                # pass 2 had nothing to settle it with when a name has two printings.
                out.append((r, [lead[0]], lead[1] or icons))
            elif icons:
                # No number in front and none behind, but the mark still names a campaign, and
                # a name is often unique inside one. Kept so pass 2 can try it, rather than
                # dropped here where nothing can look at it again. Checked AFTER the lead-in
                # form, which does have a number — just on the other side of the name.
                out.append((r, [], icons))
            continue
        nums = re.findall(r'\d+', m.group(1))
        out.append((r, [int(n) for n in nums], icons))
    return out


def _lead_ref(runs, i):
    """The citation an edition prints BEFORE the name: "<icon> 263 - Name". -> (num, [icons]).

    Walks back from the name until the previous card's name (any non-text, non-seticon run)
    or a short text budget, so it can only ever see the lead-in that belongs to this
    reference.

    No mark is required, and it cannot be: the edition prints a whole list under ONE mark —
    "<icon> 262 - Strana Soluzione (Mistura), 263 - … (Icore), 264 - … (Variante)" — so every
    entry after the first has the previous card's NAME behind it, never the mark. Requiring
    one recovered 19 of 148; not requiring it reaches the other 100.

    What keeps that safe is not a guard here but resolve() itself: a number this returns is
    only ever believed when idx.at(name, number) names exactly ONE card, so a number that is
    not a collection number simply matches nothing and the reference keeps its search link."""
    buf, k = '', i - 1
    while k >= 0 and len(buf) <= 32:
        prv = runs[k]
        if prv.get('kind') == 'text':
            buf = prv.get('t', '') + buf
        elif prv.get('kind') != 'seticon':
            break
        k -= 1
    m = _LEADNUM.search(buf.rstrip())
    return (int(re.match(r'\d+', m.group(1)).group(0)), []) if m else None


def walk(sections):
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


def learn(votes, quiet=False):
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


def confident(got):
    """Whether a learned mark is attested well enough to name a product on its own.

    One test, in one place: several references must agree, and they must agree strongly."""
    return bool(got) and got[1] >= _MIN_VOTES and got[2] >= _MIN_SHARE


def _sole_card(idx, run, nums):
    """(the number this reference really cites, the cards it names under that number).

    "( 29, 5)" is usually ONE card the publisher printed twice, and the page names the first
    printing first — so that is the one the link opens, rather than dropping the reference for
    being ambiguous. Sometimes, though, the bracket belongs to two different cards ("Dagón (…),
    Hidra (…) ( 330a, 331a)") and the name nearest it goes with the LAST number, so every number
    is tried until one names this card.

    Shared with vote(), which reads the same evidence off an already-built corpus: what counts
    as proof about a mark has to be the one thing, or the marks would be learned under one rule
    and used under another."""
    name = run.get('q') or run.get('t') or ''
    num = next((n for n in nums if idx.at(name, n)), nums[0])
    return num, idx.at(name, num)


def vote(sections, idx, grp=None):
    """What a built corpus attests each mark to be: {icon group: {cycle: votes}}.

    Pass 1's evidence, tallied without acting on it — a reference whose name and number name
    exactly ONE card teaches which campaign the mark beside it stands for.

    This exists so the marks can be learned from every edition at once (tools/iconnames.py).
    The mark is the same drawing in all four books, so evidence about it is not language-
    specific even though the books are; only which language the answer is then spelled in.

    Unlike pass 1 this does not skip a reference that already carries a code — on built data
    every resolved reference does — because the rule it applies is independent of how that code
    got there."""
    grp = iconsets.groups() if grp is None else grp
    votes = {}
    for runs in walk(sections):
        for run, nums, icons in _refs(runs):
            if not nums or not icons:
                continue
            gid = grp.get(icons[0].get('fp'), icons[0].get('fp'))
            _num, cands = _sole_card(idx, run, nums)
            if gid and len(cands) == 1 and cands[0]['cycle'] is not None:
                votes.setdefault(gid, {}).setdefault(cands[0]['cycle'], 0)
                votes[gid][cands[0]['cycle']] += 1
    return votes


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
    for runs in walk(sections):
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
        if run.get('code'):
            continue                               # already answered by hand (tools/card_links.json)
        if not nums:
            # Cited by name and mark alone. Nothing to look up here, but the mark names a
            # campaign, so pass 2 still has something to go on.
            pending.append((run, None, icons, []))
            continue
        num, cands = _sole_card(idx, run, nums)
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
    learned = learn(votes, quiet)

    # Pass 2 — the icon settles the rest.
    by_icon, by_pack, by_set, unresolved = 0, 0, 0, 0
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
        elif confident(got):
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
        # Last resort — the NAME, inside the product the mark stands for. A page whose printed
        # number ArkhamDB disagrees with, or that prints none at all, still names its card, and
        # if that product holds exactly one card of the name there is nothing left to guess.
        if confident(got):
            ref = adb.key(run.get('q') or run.get('t') or '')
            # Exact, never _close. Prefix matching is safe where a POSITION has already pinned
            # the card down; here nothing has, and run text is sometimes a piece of a longer
            # printed phrase ("Manica" out of "Asso nella Manica") that would happily steal a
            # card it merely ends with.
            if len(ref) >= 5:
                # Only products this mark's OWN confirmed references came from — a cycle is
                # coarser than a product (ArkhamDB files eight unrelated novellas and promos
                # under one), so a name unique in that bucket can still belong to a product
                # the mark does not mark.
                hits = [h for h in idx.by_cycle_all(cyc)
                        if adb.key(h['name']) == ref and pv.get(h['pack'])]
                # The two faces of one double-sided card are one answer, not two.
                if len({re.sub(r'[ab]$', '', h['code']) for h in hits}) == 1:
                    run['code'] = sorted(hits, key=_prefer)[0]['code']
                    by_set += 1
                    continue
        unresolved += 1

    # The icons now have names: a set icon can say which product it is instead of "product icon".
    named = 0
    for runs in walk(sections):
        for r in runs:
            if r.get('kind') != 'seticon':
                continue
            got = learned.get(grp.get(r.get('fp'), r.get('fp')))
            if confident(got):
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
    report = {'refs': total, 'direct': direct,
              'byname': direct - by_icon - by_pack - by_set,
              'byicon': by_icon, 'bypack': by_pack, 'byset': by_set,
              'unresolved': total - direct, 'icons': len(learned), 'named': named}
    if not quiet:
        print(f'  arkhamdb {code}: {direct}/{total} card references linked to the exact card '
              f'({report["byname"]} by name+number, {by_icon} by product icon, {by_pack} by '
              f'position, {by_set} by name within the product), {len(learned)} product icon(s) '
              f'identified, {named} icon(s) named')
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
