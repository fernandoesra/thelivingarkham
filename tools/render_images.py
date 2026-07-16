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
import langpack, card_anatomy

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
