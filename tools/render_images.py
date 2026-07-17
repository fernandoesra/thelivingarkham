# -*- coding: utf-8 -*-
"""Render this language's figures to JPEGs.

Three kinds, all declared in the pack (langs/<lang>/lang.json):
  "figures"   whole diagram pages (icon galleries, quick reference) — visual by
              nature, shown as images.
  "montages"  small card-art regions embedded inside glossary entries.
  anatomy     a section whose "kind" is "anatomy": its declared pages are read
              back out by card_anatomy.py and only the cards stay pictures. The
              cards are found on the page, so the pack names no coordinates.

Usage:  python tools/render_images.py <lang> [zoom] [quality]

Writes assets/img/<lang>-<name>.jpg plus assets/img/images_<lang>.json, a
build-time manifest that assemble.py reads to learn each figure's size. The
manifest is per language on purpose: rebuilding one language can then never
truncate another's. The rebuilt anatomy travels in it too, under "_anatomy":
finding it needs the PDF, and this is already the step that has the PDF open.
"""
import fitz, sys, os, json
from PIL import Image
import langpack, card_anatomy, icon_reference, substitution, quick_reference

IMG_DIR = os.path.join(langpack.ROOT, 'assets', 'img')


def anatomy_figures(pack):
    """The figure names an "anatomy" section declares."""
    return {n for sc in pack.sections if sc.get('kind') == 'anatomy'
            for n in sc.get('figures', [])}


def anatomy_pages(pack):
    """Which pages hold the card-anatomy chapter. The pack already answers this —
    it lists the chapter's figures, and each figure names its page — so declaring
    a section "kind": "anatomy" is the only change a pack makes to opt in."""
    byname = {f['name']: f for f in pack.figures}
    return sorted({byname[n]['page'] for n in anatomy_figures(pack) if n in byname})


ICON_DIR = os.path.join('assets', 'products')


def icon_reference_build(pack, doc):
    """Rebuild every kind='icons' chapter, and write the product art as SVG.

    The art is the same drawing in every language — the paths agree to 0.01 units in a
    0..100 viewBox — so it is written once, keyed by the product code the book prints
    untranslated beside each icon. Whichever pack builds first writes it; the rest find
    it there. Same reasoning as the game icons (langpack.icon_art_pack), and the reason
    an SVG is right rather than a JPG: it is a flat two-colour mark, it recolours from
    the theme through a CSS mask, and it is 3KB instead of 130KB."""
    out = []
    for sc in pack.sections:
        if sc.get('kind') != 'icons':
            continue
        byname = {f['name']: f for f in pack.figures}
        pages = sorted({byname[n]['page'] for n in sc.get('figures', []) if n in byname})
        for pno in pages:
            page = doc[pno - 1]
            built = icon_reference.build(page, sc)
            if not built:
                continue
            os.makedirs(ICON_DIR, exist_ok=True)
            for g in built['groups']:
                for it in g['items']:
                    box = it.pop('_box', None)
                    if not (box and it.get('art')):
                        continue
                    svg = icon_reference.icon_svg(page, box)
                    if not svg:
                        it['art'] = None
                        continue
                    with open(os.path.join(ICON_DIR, it['art'] + '.svg'), 'w',
                              encoding='utf-8') as fh:
                        fh.write(svg)
            built['key'] = sc['key']
            built.pop('qr', None)          # a page rect means nothing to the app; the
            built['qr'] = sc.get('qr')     # pack carries the link the code encodes
            out.append(built)
    return out


def substitution_build(pack, doc):
    """Rebuild every kind='substitution' table, and write its marks as SVG.

    Same reasoning as the product icons: flat two-colour marks that recolour from the
    theme through a CSS mask, drawn identically in every edition, so each is written
    once under a name taken from its own geometry and whichever pack builds first wins.

    A row is never named by its art. The book prints the SAME mark on two different
    rows — the Midnight Masks locations and its treacheries — so art that is shared is
    correct, and art used as an identity would collide."""
    out = []
    byname = {f['name']: f for f in pack.figures}
    for sc in pack.sections:
        if sc.get('kind') != 'substitution':
            continue
        made = False
        for n in sc.get('figures', []):
            f = byname.get(n)
            if not f:
                continue
            page = doc[f['page'] - 1]
            built = substitution.build(page, sc, f.get('clip'))
            if not built:
                # A section may list a figure that is not the table; that one just yields
                # nothing here. But a substitution section whose table never rebuilds on
                # the CURRENT edition is a failure, not a fallback: assemble.py has no page
                # scan to drop back to (unlike anatomy/icons), so it would ship an empty
                # entry and drop the pack's QR in silence. The per-section guard below
                # turns that into a loud stop, like every other rebuild here.
                continue
            made = True
            os.makedirs(ICON_DIR, exist_ok=True)
            art = {}
            for r in built['rows']:
                for cell in [r['from']] + r['to']:
                    box = cell.pop('_box', None)
                    svg = icon_reference.icon_svg(page, box) if box else None
                    if not svg:
                        cell['art'] = None
                        continue
                    name = substitution.fingerprint(page, box)
                    cell['art'] = name
                    prev = art.get(name)
                    if prev is None:
                        art[name] = svg
                        with open(os.path.join(ICON_DIR, name + '.svg'), 'w',
                                  encoding='utf-8') as fh:
                            fh.write(svg)
                    elif not substitution.same_art(prev, svg):
                        raise langpack.PackError(
                            f'langs/{pack.code}/lang.json: two DIFFERENT marks in section '
                            f'{sc["key"]!r} both name themselves {name!r}. The art is named '
                            f'by its own geometry, so one drawing would silently be shown '
                            f'in place of another.')
            built['key'] = sc['key']
            built.pop('qr', None)          # a page rect means nothing to the app; the
            built['qr'] = sc.get('qr')     # pack carries the link the code encodes
            if built['qr'] and not built.get('qrUnder'):
                raise langpack.PackError(
                    f'langs/{pack.code}/lang.json: section {sc["key"]!r} declares a "qr" link, '
                    f'but no heading stands above the code on its page — so there is no entry '
                    f'to show the link under, and it would be dropped in silence.')
            out.append(built)
        if not made:
            figs = ', '.join(repr(n) for n in sc.get('figures', [])) or 'none'
            raise langpack.PackError(
                f'langs/{pack.code}/lang.json: section {sc["key"]!r} is "kind": '
                f'"substitution" but no table could be rebuilt from its figure(s) ({figs}). '
                f'The page geometry did not read as a table (run tools/render_images.py to '
                f'see substitution.py\'s reason). Shipping it would blank the entry and drop '
                f'its QR silently, so the build stops instead.')
    return out


def render(doc, page, clip, zoom, quality, out):
    p = doc[page - 1]
    cl = fitz.Rect(*clip) if clip else p.rect
    pm = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=cl, alpha=False)
    im = Image.frombytes('RGB', (pm.w, pm.h), pm.samples)
    im.save(out, 'JPEG', quality=quality, optimize=True, progressive=True)
    return im.width, im.height


def render_pack(pack, outdir=IMG_DIR, zoom=2.2, quality=88):
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pack.require_pdf())
    manifest = {}

    def check_page(page, what):
        if page > doc.page_count:
            raise langpack.PackError(
                f'langs/{pack.code}/lang.json: {what} is on page {page}, but '
                f'{pack.current["pdf"]} only has {doc.page_count} pages.')

    # The anatomy chapter is read back out first, because whether that worked
    # decides whether its pages are still worth scanning at all.
    pages = anatomy_pages(pack)
    keys = card_anatomy.build(pack, pages, doc=doc) if pages else []
    # Its pages are declared as figures — that is how the pack names them — but a
    # rebuilt chapter never shows them, and they are ~1.6MB a language. So they are
    # rendered only when the rebuild came back empty and the section falls back to
    # scans (assemble.py does the matching downgrade).
    skip = anatomy_figures(pack) if keys else set()
    # The icon-reference chapter, same idea: rebuilt from the page's own vector art, so
    # the scan of it is only worth keeping if the rebuild came back empty. Its figures
    # are NOT unconditionally skipped though — an edition can print two chapters on one
    # spread and share the figure with a chapter that still needs the picture, so only
    # the ones nobody else claims are dropped.
    icons = icon_reference_build(pack, doc)
    if icons:
        mine = {n for sc in pack.sections if sc.get('kind') == 'icons' for n in sc.get('figures', [])}
        theirs = {n for sc in pack.sections if sc.get('kind') != 'icons' for n in sc.get('figures', [])}
        skip = skip | (mine - theirs)
        manifest['_icons'] = icons
    # The substitution table, same idea again — and the same care about sharing: an
    # edition that prints two book pages on one PDF page hands the same figure to two
    # sections, so only a figure nobody else still needs as a picture is dropped.
    subst = substitution_build(pack, doc)
    if subst:
        mine = {n for sc in pack.sections if sc.get('kind') == 'substitution' for n in sc.get('figures', [])}
        theirs = {n for sc in pack.sections if sc.get('kind') != 'substitution' for n in sc.get('figures', [])}
        skip = skip | (mine - theirs)
        manifest['_subst'] = subst
    # The Quick Reference sheet's text sub-sections, read off the left column (the image
    # is kept as a download, so its figure is NOT skipped). Built here because pulling the
    # prose needs the PDF open, then carried in the manifest like every other rebuild.
    qref = quick_reference.prose(pack)
    if qref:
        manifest['_quickref'] = qref
    for f in pack.figures:
        if f['name'] in skip:
            continue
        check_page(f['page'], f'figure {f["name"]!r}')
        fn = f'{pack.code}-{f["name"]}.jpg'
        w, h = render(doc, f['page'], f.get('clip'), zoom, quality, os.path.join(outdir, fn))
        manifest[f['name']] = {'file': fn, 'w': w, 'h': h, 'page': f['page']}
        print(f'  {fn}  {w}x{h}')
    # montage regions are small, so they get a higher zoom
    for m in pack.montages:
        check_page(m['page'], f'montage {m["name"]!r}')
        fn = f'{pack.code}-{m["name"]}.jpg'
        w, h = render(doc, m['page'], m['clip'], 3.0, 92, os.path.join(outdir, fn))
        manifest[m['name']] = {'file': fn, 'w': w, 'h': h, 'page': m['page']}
        print(f'  {fn}  {w}x{h}  (montage)')
    # a card is printed small and gets looked at closely, so it is rendered large
    if pages:
        # Read the callouts BEFORE erasing them: the book tucks its arrows and
        # number diamonds over the cards' edges, so a card clipped straight off
        # the page comes out with arrowheads and parchment wedges lying on it.
        # They are rebuilt as markers, so on the card itself they are damage.
        # Nothing else renders from these pages once the rebuild has succeeded.
        if keys:
            arrows = dias = 0
            for pno in pages:
                a, d = card_anatomy.strip_callouts(doc[pno - 1])
                arrows += a; dias += d
            print(f'  cleared {arrows} arrow path(s) and {dias} diamond(s) off the cards')
        for k in keys:
            for c in k['cards']:
                fn = f'{pack.code}-anat-{c["id"]}.jpg'
                c['w'], c['h'] = render(doc, c['page'], c['clip'], 3.4, 92,
                                        os.path.join(outdir, fn))
                c['file'] = fn
                c.pop('clip', None)          # a page coordinate means nothing to the app
                print(f'  {fn}  {c["w"]}x{c["h"]}  ({len(c["markers"])} marker(s))')
        manifest['_anatomy'] = keys
    path = pack.images_path(outdir)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False)
    return manifest


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/render_images.py <lang> [zoom] [quality]', file=sys.stderr)
        return 2
    pack = langpack.load(sys.argv[1])
    zoom = float(sys.argv[2]) if len(sys.argv) > 2 else 2.2
    q = int(sys.argv[3]) if len(sys.argv) > 3 else 88
    n = len(render_pack(pack, zoom=zoom, quality=q))
    print(f'  {n} figure(s) -> assets/img/images_{pack.code}.json')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
