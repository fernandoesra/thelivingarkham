# -*- coding: utf-8 -*-
"""Render each Arkham game-icon glyph to a trimmed, recolourable alpha-mask PNG
(white glyph on transparent alpha), plus a contact sheet for visual QA.

The masks are used in CSS via `-webkit-mask-image` so the app can tint them
(gold / parchment) to match the theme.

The glyphs are the same in every edition of the book, so exactly ONE pack
renders them for everybody — the one with "iconArt": {"provides": true}. Their
human-readable labels are per-language and live in each pack's ui.json.

Usage:  python tools/extract_icons.py
"""
import fitz, numpy as np, os, sys
from PIL import Image
import langpack
from icons import ICON_MAP

ICONS_DIR = os.path.join(langpack.ROOT, 'assets', 'icons')


def best_instances(doc):
    best = {}
    for pno in range(doc.page_count):
        for b in doc[pno].get_text('dict')['blocks']:
            if b['type'] != 0: continue
            for l in b['lines']:
                for s in l['spans']:
                    if 'ArkhamHorror' not in s['font']: continue
                    if len(s['text']) != 1: continue          # clean single-glyph spans only
                    cp = ord(s['text'])
                    if cp not in ICON_MAP: continue
                    h = s['bbox'][3]-s['bbox'][1]
                    if cp not in best or h > best[cp][0]:
                        best[cp] = (h, pno, fitz.Rect(s['bbox']))
    return best


def render_mask(page, rect, zoom=16, pad=1.5):
    r = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r, alpha=False)
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, pm.n)[:, :, :3].astype(float)
    lum = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    # background = brightest region; map darkness -> alpha
    hi, lo = 175.0, 60.0                     # >=hi transparent, <=lo opaque
    alpha = np.clip((hi - lum) / (hi - lo), 0, 1)
    alpha = (alpha**0.9 * 255).astype(np.uint8)
    # trim to content
    ys, xs = np.where(alpha > 20)
    if len(xs) == 0: return None
    m = int(2*zoom*0.15)
    y0,y1 = max(ys.min()-m,0), min(ys.max()+m+1, alpha.shape[0])
    x0,x1 = max(xs.min()-m,0), min(xs.max()+m+1, alpha.shape[1])
    alpha = alpha[y0:y1, x0:x1]
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:,:,0]=rgba[:,:,1]=rgba[:,:,2]=255   # white glyph; recolour via CSS mask
    rgba[:,:,3]=alpha
    return Image.fromarray(rgba, 'RGBA')


def _cap(im, limit=256):
    if im.height > limit:
        w = int(im.width * limit / im.height)
        im = im.resize((max(w, 1), limit), Image.LANCZOS)
    return im


def build(pack, outdir=ICONS_DIR):
    """Render every glyph mask from the icon-art pack's PDF."""
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pack.require_pdf())
    best = best_instances(doc)
    imgs = {}
    for cp, name in ICON_MAP.items():
        if cp not in best:
            print('  MISSING', name); continue
        _h, pno, rect = best[cp]
        im = render_mask(doc[pno], rect)
        if im is None:
            print('  EMPTY', name); continue
        im = _cap(im)
        im.save(os.path.join(outdir, name + '.png'))
        imgs[name] = im
    # symbols drawn as PDF vectors (e.g. the basic-weakness symbol): neither the
    # text parser nor the icon font ever sees them, so they are clipped by hand.
    for name, sm in pack.icon_art.get('symbols', {}).items():
        im = render_mask(doc[sm['page']-1], fitz.Rect(*sm['rect']), zoom=10, pad=1)
        if im is None:
            print('  EMPTY', name); continue
        im = _cap(im)
        im.save(os.path.join(outdir, name + '.png'))
        imgs[name] = im
    contact_sheet(imgs, outdir)
    print(f'  {len(imgs)} icon masks -> assets/icons/  (from the {pack.code} pack)')
    return imgs


def contact_sheet(imgs, outdir):
    names = list(imgs); cols = 6; rows = (len(names)+cols-1)//cols; cell = 120
    if not names:
        return
    sheet = Image.new('RGBA', (cols*cell, rows*cell), (30, 34, 42, 255))
    for i, nm in enumerate(names):
        im = imgs[nm].copy()
        s = min((cell-36)/im.width, (cell-36)/im.height)
        im = im.resize((max(int(im.width*s), 1), max(int(im.height*s), 1)), Image.LANCZOS)
        gold = Image.new('RGBA', im.size, (212, 175, 55, 255)); gold.putalpha(im.split()[3])
        cx = i % cols*cell+(cell-im.width)//2; cy = i//cols*cell+(cell-im.height)//2-6
        sheet.alpha_composite(gold, (cx, cy))
    sheet.save(os.path.join(outdir, '_contact_sheet.png'))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    packs, _errs = langpack.load_valid()      # a broken pack must not stop the icons
    art = langpack.icon_art_pack(packs)
    if art is None:
        print('  [skip] no pack sets "iconArt": {"provides": true} — nothing to render.')
        return 0
    if not art.has_pdf():
        # The masks are committed to the repo, so a contributor who does not have
        # the icon-art PDF is fine: their language reuses the existing artwork.
        print(f'  [skip] the {art.code} pack renders the game icons, but its PDF is not here.\n'
              f'         Using the icons already in assets/icons/ — this is normal unless you '
              f'are re-rendering them.')
        return 0
    build(art)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
