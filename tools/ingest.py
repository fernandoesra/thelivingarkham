# -*- coding: utf-8 -*-
"""Content pipeline: each language's source PDF -> data/ + assets/.

    python tools/ingest.py            every language pack
    python tools/ingest.py de         just German
    python tools/ingest.py de en      German and English

Run it after adding a language pack, or when a new Grimoire version comes out.
It is not needed to run or host the site: the app is plain static files, and
everything this writes is committed to the repo.

Requires Python 3.9+ with the packages in tools/requirements.txt.
"""
import os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import langpack                                  # noqa: E402
import parse_grimoire, render_images, extract_icons, assemble, validate_coverage, history  # noqa: E402

IMG_DIR = os.path.join(langpack.ROOT, 'assets', 'img')


def step(msg):
    print(f'\n== {msg} ==')


def run_pack(pack, all_packs):
    """Build one language. Raises PackError with an author-facing message."""
    import json
    step(f'{pack.code} — {pack.name} (v{pack.current["v"]}, {pack.current["pdf"]})')
    pack.require_pdf()

    print('-- parse PDF')
    nodes, _doc = parse_grimoire.parse(pack)
    os.makedirs(langpack.DATA_DIR, exist_ok=True)
    with open(pack.nodes_path, 'w', encoding='utf-8') as f:
        json.dump(nodes, f, ensure_ascii=False)
    print(f'  {len(nodes)} nodes -> data/_nodes_{pack.code}.json')
    parse_grimoire.warn_if_no_red(pack, nodes)

    print('-- render figures')
    images = render_images.render_pack(pack, outdir=IMG_DIR)

    print('-- assemble grimoire JSON')
    intro, sections, title_index = assemble.assemble(pack, nodes, images)
    allsecs = [intro] + sections

    added = changed = None
    if len(pack.versions) > 1:
        print('-- version history (comparing the editions)')
        newest = {}
        for s in allsecs:
            if s.get('intro'):
                newest[history.SEC + s['id']] = {'blocks': s['intro']}
            for e in s.get('entries', []):
                newest[e['id']] = e
        added, changed, parsed, notes = history.build(pack, newest_units=newest)
        for n in notes:
            print(f'  [note] {n}')

    versions, whatsnew = assemble.apply_versions(allsecs, pack, added, changed)
    links = assemble.linkify(allsecs, title_index, pack)
    autolinks = assemble.autolink(allsecs, title_index, pack)
    data = {'lang': pack.code, 'sections': allsecs, 'versions': versions, 'whatsnew': whatsnew}
    with open(pack.data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    total = sum(len(s['entries']) for s in allsecs)
    print(f'  {len(allsecs)} sections · {total} entries · {links} cross-links · '
          f'{autolinks} auto-links -> data/grimoire_{pack.code}.json')
    for v in versions:
        wn = whatsnew.get(v['v'])
        if wn:
            print(f'  v{v["v"]}: {len(wn["new"])} new entries, {len(wn["updated"])} rewritten')

    print('-- check the parsed text against the PDF')
    validate_coverage.report(pack, data)
    verify_labels(pack, all_packs)
    return total


def verify_labels(pack, all_packs):
    """A missing icon label is not fatal — the app falls back to the icon's name —
    but the translator should hear about it."""
    from icons import icon_names
    known = icon_names(all_packs)
    have = pack.ui.get('icons', {})
    missing = [n for n in known if not have.get(n)]
    if missing:
        print(f'  [warn] langs/{pack.code}/ui.json has no "icons" label for: '
              f'{", ".join(missing)}\n'
              f'         Readers will see the raw name in the tooltip instead.')


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    flags = [a for a in argv if a.startswith('-')]
    if flags:
        # Silently ignoring them would turn `ingest.py --de` (a plausible typo)
        # into a full rebuild of every language.
        print(f'{__doc__.strip()}\n\nUnknown option: {flags[0]}', file=sys.stderr)
        return 2
    only = list(argv) or None
    t0 = time.time()
    if not langpack.codes():
        print('No language packs found under langs/.\n'
              'Start one with:  python tools/new_lang.py <code>')
        return 1

    # A pack that fails to load is reported and skipped: a language you are not
    # even building must never stop the ones you are.
    packs, failed = langpack.load_valid(only)
    for code, msg in failed:
        print(f'\nERROR in the {code} pack:\n{msg}', file=sys.stderr)

    step('game icons (shared by every language)')
    # The masks are committed, so a failure here costs nothing but freshness —
    # it must never stop the languages from building.
    try:
        extract_icons.main()
    except Exception as e:
        print(f'  [warn] could not re-render the game icons: {e}\n'
              f'         Using the ones already in assets/icons/.', file=sys.stderr)

    built = 0
    for pack in packs:
        try:
            run_pack(pack, packs)
            built += 1
        except langpack.PackError as e:
            failed.append((pack.code, str(e)))
            print(f'\nERROR in the {pack.code} pack:\n{e}', file=sys.stderr)
        except Exception:
            failed.append((pack.code, 'unexpected error (traceback above)'))
            traceback.print_exc()

    step('language registry')
    langpack.write_registry()

    total = len(packs) + len([1 for c, _ in failed if c not in [p.code for p in packs]])
    print(f'\n== done in {time.time()-t0:.0f}s — {built}/{total} language(s) built ==')
    if failed:
        print('\nFAILED: ' + ', '.join(c for c, _ in failed), file=sys.stderr)
        print('The other languages were still written. Fix the message above and re-run '
              'just that language, e.g.  python tools/ingest.py ' + failed[0][0], file=sys.stderr)
        return 1
    print('Preview with:  npm run dev')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
