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
import faq                                        # noqa: E402

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

    if len(pack.versions) > 1:
        print('-- version history (comparing the editions)')
    # One shared path with tools/assemble.py — history, versions, links, the
    # Ultimatums & Boons viewer, groupOrder — so a build here matches a build there.
    data, rep = assemble.finalize(pack, allsecs, title_index)
    with open(pack.data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    versions, whatsnew, links, autolinks = (
        rep['versions'], rep['whatsnew'], rep['links'], rep['autolinks'])
    total = sum(len(s['entries']) for s in allsecs)
    print(f'  {len(allsecs)} sections · {total} entries · {links} cross-links · '
          f'{autolinks} auto-links -> data/grimoire_{pack.code}.json')
    for v in versions:
        wn = whatsnew.get(v['v'])
        if wn:
            print(f'  v{v["v"]}: {len(wn["new"])} new entries, {len(wn["updated"])} rewritten')
    if rep['ub']:
        u = rep['ub']
        print(f'  ultimatums viewer: {u["ultimatums"]} ultimatum(s), {u["boons"]} boon(s), '
              f'{u["refractions"]} refraction(s)')

    print('-- check the parsed text against the PDF')
    validate_coverage.report(pack, data)
    verify_labels(pack, all_packs)

    # The FAQ chapter 1 corpus, if this language has one. Built after the Grimoire
    # because its cross-references link into the Grimoire (see tools/faq.py). A missing
    # or malformed FAQ is a warning, never fatal — the Grimoire is already written.
    print('-- assemble FAQ chapter 1 JSON')
    try:
        fdata, frep = faq.build(pack, data)
        if fdata is None:
            print('  (no "faq" declared for this language — skipped)')
        else:
            with open(faq.data_path(pack.code), 'w', encoding='utf-8') as f:
                json.dump(fdata, f, ensure_ascii=False)
            print(f'  {frep["sections"]} sections · {frep["entries"]} entries · '
                  f'{frep["cards"]} card links · {frep["links"]} cross-refs · '
                  f'{frep["autolinks"]} auto-links -> data/faq_{pack.code}.json')
    except langpack.PackError as e:
        print(f'  [warn] FAQ chapter 1 not built for {pack.code}: {e}')
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

    # Fill the Ultimatums & Boons viewer across languages: cards English has and the
    # others do not yet are shown in English, flagged. Needs every language built first,
    # so it runs here, once, after the loop — never inside a single pack's build.
    if built:
        step('ultimatums & boons — cross-language fill')
        import ub_merge
        try:
            ub_merge.merge()
        except Exception as e:
            print(f'  [warn] cross-language fill skipped: {e}', file=sys.stderr)

    # The FAQ chapter-1 refractions: pair each with its imported card and append it to the
    # Grimoire's ub.refractions, tagged chapter='cap1' (existing items get 'both'/'cap2'), so
    # the viewer's chapter filter can show cap 1, cap 2 or all. Runs AFTER the cross-language
    # fill so its campaign-ordered refractions are the final word (ub_merge sorts by name).
    # The scenario (encounter-set) symbols the refraction cards show, cut from the artist's vector
    # sheets. Those live outside the repo, so this is best-effort: without them the committed
    # assets/products/scen-*.svg are kept.
    if built:
        step('scenario icons — from the vector symbol sheets')
        try:
            import scenario_icons
            scenario_icons.build()
        except Exception as e:
            print(f'  [warn] scenario icons not refreshed (keeping the committed ones): '
                  f'{type(e).__name__}: {e}', file=sys.stderr)

    if built:
        step('ultimatums & boons — FAQ chapter-1 refractions')
        import ub_cap1
        for pack in packs:
            try:
                ub_cap1.build(pack)
            except Exception as e:
                print(f'  [warn] chapter-1 refractions skipped for {pack.code}: {e}', file=sys.stderr)

    if built:
        # One drawing per mark, shared by every language. Runs after the corpora are
        # written and before the orphan report, so the report sees the final references.
        step('shared art — one drawing per product mark')
        import artshare
        artshare.consolidate()
        # …and one record per card. After artshare, so the symbols it writes into the shared
        # record are already the canonical ones.
        import ub_registry
        ub_registry.build([p.code for p in packs])
        # A mark is one drawing in all four books, so what any edition proves about it is
        # proof for the others too. Pooled here rather than inside a pack's own build, where
        # it could only ever see one book's evidence — and reading every language's data, not
        # just the ones this run touched, so a single-language rebuild keeps the names.
        import iconnames
        iconnames.build([p.code for p in packs])
        # Anything the icon tables could not name a product for, written down so it can be
        # answered by hand (tools/other/icon-products-unmatched.md).
        import packmap
        # Complete each book's icon table with the products it left out — after artshare, so
        # the drawing copied across is the canonical one.
        packmap.complete()
        # …and add the products no edition prints at all, from our own sourced icons.
        packmap.add_extras()
        n = packmap.report(packmap.MISSED)
        print(f'  {n} icon row(s) with no product identity -> tools/other/icon-products-unmatched.md')
        import faq_seticons as _fs
        _fs.report_orphans()
        import adb_names as _an
        _an.report_unused()

    # The interactive taboo list is fetched from ArkhamDB (tools/taboos.py). Network, so it is
    # best-effort: if it fails (offline, API down) the committed data/taboos_<code>.json is kept.
    if built:
        step('taboo list — from ArkhamDB')
        import taboos
        for pack in packs:
            try:
                taboos.build_and_write(pack.code)
            except Exception as e:
                print(f'  [warn] taboo list not refreshed for {pack.code} '
                      f'(keeping the committed one): {type(e).__name__}: {e}', file=sys.stderr)

    # Now that every corpus has been through, say which curated corrections found nothing.
    if built:
        import text_fixes
        text_fixes.report_unused()

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
