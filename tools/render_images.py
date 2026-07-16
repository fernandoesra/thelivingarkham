# -*- coding: utf-8 -*-
"""Render this language's figures to JPEGs.

Two kinds, both declared in the pack (langs/<lang>/lang.json):
  "figures"   whole diagram pages (card anatomy, icon galleries, quick reference)
              — visual by nature, shown as images.
  "montages"  small card-art regions embedded inside glossary entries.

Usage:  python tools/render_images.py <lang> [zoom] [quality]

Writes assets/img/<lang>-<name>.jpg plus assets/img/images_<lang>.json, a
build-time manifest that assemble.py reads to learn each figure's size. The
manifest is per language on purpose: rebuilding one language can then never
truncate another's.
"""
import fitz, sys, os, json
from PIL import Image
import langpack

IMG_DIR = os.path.join(langpack.ROOT, 'assets', 'img')


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

    for f in pack.figures:
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
