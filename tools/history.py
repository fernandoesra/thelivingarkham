# -*- coding: utf-8 -*-
"""When each entry appeared, and when it changed.

The Grimoire is a living document: every edition adds and rewrites entries, and
prints the added text in dark red. Two different questions follow from that, and
they must not be confused:

  Is this entry NEW?      Answerable only by looking at the previous edition.
  What text is new in it? Answerable from the red markup in this edition.

Reading the red alone cannot separate them. In the English v1.1 fourteen entries
carry a red heading, but only ONE ("Search") is absent from v1.0 — the other
thirteen are existing entries the publisher rewrote. "Replenish" is 96% red and
still not new. So a threshold on "how much of it is red" cannot work either.

Therefore: parse every edition the pack ships and compare them. An entry is new
in the first edition that contains it; it changed in any later edition that
prints red inside it. Editions that are declared but whose PDF is absent are
skipped, and what that costs is reported rather than guessed at.
"""
import contextlib
import io as _io
import os

import langpack
import parse_grimoire as P
import assemble


# A chapter's own lead text is content too: the English v1.1 adds 3,000 characters
# of new FAQ answers that live in the FAQ chapter's intro, not in any entry. Track
# both, keyed the way the site addresses them.
SEC = 'sec:'


@contextlib.contextmanager
def _quiet():
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


def _units_of(pack, nodes):
    """Everything one edition can change, keyed by the id the site will use:
    each entry, and each chapter's own intro."""
    # Figures are irrelevant to a comparison, so none are passed — which would
    # otherwise print a 'montage not attached' warning per figure, per edition.
    with _quiet():
        intro, sections, _title_index = assemble.assemble(pack, nodes, {})
    out = {}
    for s in [intro] + sections:
        if s.get('intro'):
            out[SEC + s['id']] = {'blocks': s['intro']}
        for e in s.get('entries', []):
            out[e['id']] = e
    return out


def _has_red(unit):
    return any(r.get('red') for b in unit['blocks'] for r in b['runs'])


def build(pack, newest_units=None, verbose=True):
    """-> (added, changed, parsed_versions, notes)

    added[id]   = version the unit first appeared in, or None if unknowable
                  (its edition was never parsed, so we must not claim it is new)
    changed[id] = [versions in which the publisher marked changes inside it]

    Ids are entry ids, plus 'sec:<section id>' for a chapter's own intro.
    """
    added, changed, notes = {}, {}, []
    parsed = []
    declared = [v['v'] for v in pack.versions]

    for i, v in enumerate(pack.versions):
        pdf = os.path.join(pack.dir, 'source', v['pdf'])
        if not os.path.exists(pdf):
            notes.append(f'v{v["v"]}: {v["pdf"]} is not in langs/{pack.code}/source/, '
                         f'so nothing can be said about what changed in it')
            continue
        is_newest = (i == len(pack.versions) - 1)
        if is_newest and newest_units is not None:
            units = newest_units              # already parsed for the site itself
        else:
            # Older editions are read only to compare against: their montage
            # clips belong to a different layout, so no masking is applied.
            nodes, _doc = P.parse_pdf(pdf, masks={})
            try:
                units = _units_of(pack, nodes)
            except langpack.PackError as e:
                # An old edition may not have every chapter the newest one has.
                # That is history, not a broken pack — note it and move on.
                notes.append(f'v{v["v"]}: could not be compared ({str(e).splitlines()[0]})')
                continue
        parsed.append(v['v'])

        if len(parsed) > 1:
            origin = v['v']          # a later edition: whatever is new here arrived here
        elif i == 0:
            origin = v['v']          # the book's first edition: everything in it started here
        else:
            # The oldest edition we can read is not the book's first, so an entry
            # already in it may be older still. Unknown — never claim "new".
            origin = None

        for uid, u in units.items():
            if uid not in added:
                added[uid] = origin
            # Red inside something we have seen before = the publisher rewrote it.
            # Something that arrives in this very edition is new, not rewritten.
            if _has_red(u) and added.get(uid) != v['v']:
                changed.setdefault(uid, []).append(v['v'])
        if verbose:
            n_e = sum(1 for k in units if not k.startswith(SEC))
            print(f'  read v{v["v"]}: {n_e} entries, {len(units)-n_e} chapter intros')

    if not parsed:
        notes.append('no edition could be read, so there is no version history')
    else:
        gaps = [x for x in declared if x not in parsed]
        if gaps:
            which = 'those editions' if len(gaps) > 1 else 'that edition'
            notes.append(f'no PDF for v{", v".join(gaps)} — changes made in {which} are '
                         f'credited to the next edition that has one. Add the file to '
                         f'langs/{pack.code}/source/ for an exact history.')
    return added, changed, parsed, notes


def whatsnew_index(allsecs, added, changed, versions):
    """Per version: what arrived, and what was rewritten.

    Chapters count as well as entries: the FAQ chapter gained five whole Q&As in
    the English v1.1 and they live in its intro, so listing only entries would
    leave the edition's most useful additions out of its own changelog.
    """
    index = {}
    first = versions[0]['v']

    def add(uid, item):
        a = added.get(uid)
        if a and a != first:
            index.setdefault(a, {'new': [], 'updated': []})['new'].append(item)
        for v in changed.get(uid, []):
            index.setdefault(v, {'new': [], 'updated': []})['updated'].append(item)

    for s in allsecs:
        if s.get('intro'):
            # the chapter itself: clicking it opens the chapter
            add(SEC + s['id'], {'id': s['id'], 'title': s['title'], 'sid': s['id'],
                                'sec': s['title'], 'num': s['num'], 'chapter': True})
        for e in s.get('entries', []):
            item = {'id': e['id'], 'title': e['title'], 'sid': s['id'],
                    'sec': s['title'], 'num': s['num']}
            # A title can contain a game icon — "Unique ()" is a word and a glyph.
            # The plain string keeps that glyph as its raw codepoint in the icon
            # font, and nothing on the page is set in that font, so on its own it
            # renders as tofu. The runs carry the icon as an icon.
            if e.get('titleRuns'):
                item['titleRuns'] = e['titleRuns']
            add(e['id'], item)
    return index
