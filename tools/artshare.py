# -*- coding: utf-8 -*-
"""One drawing per product, shared by every language.

A product's mark is the same picture in every edition — "The Drowned City" is one symbol,
printed in four books. But each edition draws it with its own rounding, so tracing it four
times lands on four different fingerprints and the repo ends up holding four files for one
mark: 163 art files for ~80 real symbols, and 81 of them referenced by a single language.
That is not a translation problem, it is a storage one, and it gets worse with every
language added.

So after the languages are built, the traced art is grouped BY PICTURE — the same
comparison tools/iconsets.py already uses to tell which product an inline mark belongs to
— and every reference is pointed at one file per group. The pictures are unchanged; what
changes is that four names for one drawing become one.

Every data file is rewritten, not just the language that was rebuilt, so no corpus is left
pointing at a name another one has moved off.

WHAT THIS DOES NOT DO IS DELETE THE TRACED FILES, and that is deliberate — it was tried and
it broke something quietly. The traced fingerprints are not redundant copies: they are the
evidence tools/adb_resolve.py reasons over. It groups near-identical marks by shape
(tools/iconsets.py) so that all of a product's references vote together for what its icon
means, and that is how a set icon earns a real name ("Legado de Dunwich") instead of
"product icon". Deleting the siblings took the votes away with them: English dropped from
485 named icons to 398, Spanish from 462 to 427 — a silent accessibility regression, since
the name is what a screen reader reads out. So the marks stay; what changes is that every
language now POINTS at one of them.

It is checkable: a group whose members are captioned with different product names in the
same language would mean two different marks were merged, and that is reported.
"""
import collections
import glob
import json
import os
import re

import iconsets
import langpack

PRODUCTS_DIR = os.path.join(langpack.ROOT, 'assets', 'products')
FAQSETS_DIR = os.path.join(langpack.ROOT, 'assets', 'faqsets')

# A traced name is a fingerprint ("fc-6-9264a7b8", "e5-6cc1b92c"); anything else was named
# by a person ("return-night-of-the-zealot", "faq-coreset", "AHC100") and is the better
# name to keep, because it says what the mark IS.
_TRACED = re.compile(r'^(?:fc-)?e?\d+-[0-9a-f]{8}$')


def _canonical(members):
    """The name a group keeps: a hand-given one if it has one, else the first traced name
    (alphabetical, so the choice does not depend on the order the files were made)."""
    named = sorted(m for m in members if not _TRACED.match(m))
    return named[0] if named else sorted(members)[0]


def _plan(directory):
    """-> {name: canonical name} for one directory, identity entries left out."""
    by_group = {}
    for fp, gid in iconsets.groups(directory).items():
        by_group.setdefault(gid, []).append(fp)
    plan = {}
    for members in by_group.values():
        keep = _canonical(members)
        for m in members:
            if m != keep:
                plan[m] = keep
    return plan


def _data_files():
    return sorted(glob.glob(os.path.join(langpack.DATA_DIR, 'faq_*.json'))
                  + glob.glob(os.path.join(langpack.DATA_DIR, 'grimoire_*.json'))
                  + glob.glob(os.path.join(langpack.DATA_DIR, 'taboos_*.json')))


def _rewrite(path, plan):
    """Repoint this file's art references. -> number of references changed."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    n = [0]

    def walk(o):
        if isinstance(o, dict):
            for key in ('art', 'fp', 'collection'):
                v = o.get(key)
                if isinstance(v, str) and v in plan:
                    o[key] = plan[v]
                    n[0] += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    if n[0]:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    return n[0]


def _referenced():
    """Every art name any built corpus still points at."""
    used = set()
    for path in _data_files():
        with open(path, encoding='utf-8') as f:
            used |= set(re.findall(r'"(?:art|fp|collection)":\s*"([^"]+)"', f.read()))
    return used


def _captions(plan):
    """{canonical: {language: {product name, …}}} — what each group is called where.

    Only the set marks carry a caption (`pn`, the product the mark stands for), and it is
    the evidence that a group is one mark: two names in one language means two marks were
    merged into one file, which is the only way this step can do damage."""
    out = {}
    for path in _data_files():
        code = os.path.basename(path).rsplit('_', 1)[-1][:-5]
        with open(path, encoding='utf-8') as f:
            for fp, pn in re.findall(r'"fp":\s*"([^"]+)",\s*"pn":\s*"([^"]*)"', f.read()):
                if pn:
                    out.setdefault(plan.get(fp, fp), {}).setdefault(code, set()).add(pn)
    return out


def _by_product():
    """{art name: canonical art name} for rows that name the same PRODUCT.

    The picture grouping below can only unite drawings that LOOK alike, and editions do not
    always draw a mark alike: the German book sets its "Rückkehr zu…" marks on a square plate
    where every other edition uses a disc, so no amount of comparing pictures will unite them.
    What does unite them is that the rows say the same product (tools/packmap.py). The drawing
    the most languages already agree on wins, so the odd edition out follows the majority
    rather than the other way round."""
    votes = {}
    for path in _data_files():
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for s in data.get('sections', []):
            if s.get('kind') != 'icons':
                continue
            for g in s.get('groups', []) or []:
                for it in g.get('items', []) or []:
                    pack, art = it.get('pack'), it.get('art')
                    if pack and art:
                        votes.setdefault(pack, collections.Counter())[art] += 1
    plan = {}
    for pack, arts in votes.items():
        if len(arts) < 2:
            continue                     # every language already shows the same drawing
        keep = sorted(arts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for art in arts:
            if art != keep:
                plan[art] = keep
    return plan


def consolidate(quiet=False):
    """Point every language at one file per mark. -> (groups collapsed, files removed)."""
    def say(*a):
        if not quiet:
            print(*a)

    plan = {}
    for directory in (PRODUCTS_DIR, FAQSETS_DIR):
        if os.path.isdir(directory):
            plan.update(_plan(directory))
    # …then by product, which catches the marks the editions genuinely draw differently.
    # Applied over the shape plan, so a name already folded onto a canonical one follows it.
    byprod = _by_product()
    for a, b in byprod.items():
        plan[a] = plan.get(b, b)
    if not plan:
        say('  art: nothing to share')
        return 0, 0

    changed = sum(_rewrite(p, plan) for p in _data_files())

    # Over-merge check, before anything is deleted.
    for canon, langs in _captions(plan).items():
        for code, names in langs.items():
            if len(names) > 1:
                say(f'  [warn] {canon} is captioned {sorted(names)} in {code} — two marks '
                    f'may have been merged into one file. Nothing was deleted for it.')

    used = _referenced()
    kept = len({v for v in plan.values()})
    say(f'  {len(plan)} duplicate name(s) folded onto {kept} shared mark(s); '
        f'{changed} reference(s) repointed; {len(used)} mark(s) now shown, '
        f'the rest kept as the resolver\'s evidence (see the note at the top of this file)')
    return kept, len(used)


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    consolidate()


if __name__ == '__main__':
    main()
