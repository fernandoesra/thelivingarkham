# -*- coding: utf-8 -*-
"""Render diagram-heavy pages (card anatomy, icon galleries, quick reference)
to JPEG figures. These sections are visual by nature and are shown as images."""
import fitz, sys, os, json
from PIL import Image
import io

def render(doc, page, clip, zoom, quality, out):
    p = doc[page-1]
    cl = fitz.Rect(*clip) if clip else p.rect
    pm = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=cl, alpha=False)
    im = Image.frombytes('RGB', (pm.w, pm.h), pm.samples)
    im.save(out, 'JPEG', quality=quality, optimize=True, progressive=True)
    return im.width, im.height

# name, page, clip(x0,y0,x1,y1 or None=full)
JOBS = {
 'es': ('AHLCG_Grimorio_v_1_0_Capitulo2.pdf', [
    ('card-location',   34, None),
    ('card-agenda-act-treachery-enemy', 35, None),
    ('card-investigator',36, None),
    ('card-asset-event-skill', 37, None),
    ('icons-products',   46, (2, 150, 305, 705)),
    ('icons-encounter-1',47, None),
    ('icons-encounter-2',48, None),
    ('quick-reference',  49, None),
 ]),
 'en': ('arkham_grimoire_v11.pdf', [
    ('card-anatomy-1', 17, None),
    ('card-anatomy-2', 18, None),
    ('icons-ref-a',    23, None),
    ('icons-ref-b',    24, None),
 ]),
}

if __name__ == '__main__':
    grimdir = sys.argv[1]      # folder with the PDFs
    outdir = sys.argv[2]
    zoom = float(sys.argv[3]) if len(sys.argv) > 3 else 2.2
    q = int(sys.argv[4]) if len(sys.argv) > 4 else 88
    os.makedirs(outdir, exist_ok=True)
    manifest = {}
    for lang, (pdf, jobs) in JOBS.items():
        if not jobs:
            continue
        doc = fitz.open(os.path.join(grimdir, pdf))
        for name, page, clip in jobs:
            fn = f'{lang}-{name}.jpg'
            w, h = render(doc, page, clip, zoom, q, os.path.join(outdir, fn))
            manifest.setdefault(lang, {})[name] = {'file': fn, 'w': w, 'h': h, 'page': page}
            print(f'  {fn}  {w}x{h}')
    json.dump(manifest, open(os.path.join(outdir, 'images.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('done')
