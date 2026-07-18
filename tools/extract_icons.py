# -*- coding: utf-8 -*-
"""Turn the game's icon font into recolourable icons for the web.

The icons are glyphs in the Arkham font embedded in the Grimoire PDF. Two things
have to survive the trip, and one of them used to not:

  the SHAPE — traced from the font outlines, so it is vector and stays sharp.
  the SIZE  — a font knows exactly how big each glyph is and where it sits on
              the baseline. "Unique" is a small 0.41em mark at x-height; "free"
              is a wide 2.12em arrow. Rendering both into the same square box is
              what made Unique 2.7x too big and Free less than half its size.

So each icon is emitted with its own true measurements, and `icons.css` sizes it
the way the font would: width, height and baseline offset in em. The result is an
icon that sits in a sentence exactly as it does on the printed page.

Symbols drawn as vector art rather than typed (the basic-weakness symbol) are not
in the font, so they are still clipped from the page to a PNG mask.

Usage:  python tools/extract_icons.py
"""
import fitz, numpy as np, os, sys
from PIL import Image
import langpack
from icons import ICON_MAP

ICONS_DIR = os.path.join(langpack.ROOT, 'assets', 'icons')
CSS_PATH = os.path.join(langpack.ROOT, 'css', 'icons.css')

# A few glyphs are genuinely tiny in the font — "unique" is a 0.39em mark meant to
# sit before a card's name, and at that size on a screen it is a speck. Anything
# shorter than this is grown to it, keeping its own proportions and the point it
# sits at. Everything else (0.8–0.9em) is left exactly as the font drew it.
MIN_HEIGHT_EM = 0.62


# ---- the font ---------------------------------------------------------------
def extract_font(doc, outdir):
    """Pull the embedded Arkham icon font out of the PDF."""
    for pno in range(doc.page_count):
        for f in doc.get_page_fonts(pno):
            if 'ArkhamHorror' not in f[3]:
                continue
            _name, ext, _ftype, buf = doc.extract_font(f[0])
            path = os.path.join(outdir, '_font.' + ext)
            with open(path, 'wb') as fh:
                fh.write(buf)
            return path
    return None


def glyph_ids(doc):
    """codepoint -> glyph id, read from the PDF itself.

    The embedded font is a subset with no cmap, so the codepoint cannot be looked
    up in the font: the PDF's own text trace is what knows which glyph each
    character maps to.
    """
    out = {}
    for pno in range(doc.page_count):
        for span in doc[pno].get_texttrace():
            if 'ArkhamHorror' not in span.get('font', ''):
                continue
            for ch in span['chars']:
                if ch[0] in ICON_MAP:
                    out.setdefault(ch[0], ch[1])
    return out


def trace_glyphs(font_path, gids):
    """-> {name: (svg_text, width_em, height_em, baseline_em)}"""
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.roundingPen import RoundingPen
    from fontTools.pens.boundsPen import BoundsPen

    font = TTFont(font_path)
    gs = font.getGlyphSet()
    order = font.getGlyphOrder()
    upm = font['head'].unitsPerEm
    out = {}
    for cp, name in sorted(ICON_MAP.items(), key=lambda kv: kv[1]):
        gid = gids.get(cp)
        if gid is None or gid >= len(order):
            print(f'  [warn] {name}: U+{cp:04X} never appears in this PDF, so its glyph '
                  f'could not be identified — keeping any existing icon')
            continue
        gname = order[gid]
        bp = BoundsPen(gs)
        gs[gname].draw(bp)
        if not bp.bounds:
            print(f'  [warn] {name}: the glyph is empty')
            continue
        x0, y0, x1, y1 = bp.bounds
        w, h = x1 - x0, y1 - y0

        pen = SVGPathPen(gs, ntos=lambda v: str(int(round(v))))
        # font y grows up, SVG y grows down: flip, and move the ink to the origin
        gs[gname].draw(TransformPen(RoundingPen(pen), (1, 0, 0, -1, -x0, y1)))
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}">'
               f'<path d="{pen.getCommands()}"/></svg>\n')
        w_em, h_em, base_em = w / upm, h / upm, y0 / upm
        if h_em < MIN_HEIGHT_EM:
            grow = MIN_HEIGHT_EM / h_em
            w_em, h_em, base_em = w_em * grow, MIN_HEIGHT_EM, base_em * grow
            print(f'  {name} is only {h/upm:.2f}em tall in the font — grown {grow:.1f}x to stay legible')
        out[name] = (svg, w_em, h_em, base_em)
    return out


def fill_from_faq(glyphs, outdir):
    """Trace any ICON_MAP glyph the Grimoire font does not carry from a FAQ font.

    The Grimoire never prints some game icons (the bless/curse chaos tokens), so their
    glyphs are absent from its embedded font. The FAQ documents do print them, in the
    same icon font family with the same private-use codepoints, so the missing shapes
    are traced from the first FAQ PDF that has them. Only genuinely-missing names are
    filled — the Grimoire stays the canonical source for every icon it does carry."""
    missing = set(ICON_MAP.values()) - set(glyphs)
    if not missing:
        return glyphs
    for code in langpack.codes():
        faq_dir = os.path.join(langpack.LANGS_DIR, code, 'source_faq')
        if not os.path.isdir(faq_dir):
            continue
        for fname in sorted(os.listdir(faq_dir)):
            if not fname.lower().endswith('.pdf'):
                continue
            doc = fitz.open(os.path.join(faq_dir, fname))
            font_path = extract_font(doc, outdir)
            if not font_path:
                continue
            traced = trace_glyphs(font_path, glyph_ids(doc))
            os.remove(font_path)
            added = []
            for name in list(missing):
                if name in traced:
                    with open(os.path.join(outdir, name + '.svg'), 'w', encoding='utf-8',
                              newline='\n') as f:
                        f.write(traced[name][0])
                    glyphs[name] = traced[name]
                    missing.discard(name)
                    added.append(name)
            if added:
                print(f'  {len(added)} icon(s) filled from the {code} FAQ font: '
                      f'{", ".join(sorted(added))} -> assets/icons/*.svg')
            if not missing:
                return glyphs
    if missing:
        print(f'  [warn] these ICON_MAP icons were in no available font: {", ".join(sorted(missing))}')
    return glyphs


# ---- drawn symbols (not in the font) ----------------------------------------
def render_mask(page, rect, zoom=16, pad=1.5):
    r = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r, alpha=False)
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, pm.n)[:, :, :3].astype(float)
    lum = 0.299*a[:, :, 0] + 0.587*a[:, :, 1] + 0.114*a[:, :, 2]
    hi, lo = 175.0, 60.0                     # >=hi transparent, <=lo opaque
    alpha = np.clip((hi - lum) / (hi - lo), 0, 1)
    alpha = (alpha**0.9 * 255).astype(np.uint8)
    ys, xs = np.where(alpha > 20)
    if len(xs) == 0:
        return None
    m = int(2*zoom*0.15)
    y0, y1 = max(ys.min()-m, 0), min(ys.max()+m+1, alpha.shape[0])
    x0, x1 = max(xs.min()-m, 0), min(xs.max()+m+1, alpha.shape[1])
    alpha = alpha[y0:y1, x0:x1]
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:, :, 0] = rgba[:, :, 1] = rgba[:, :, 2] = 255   # white glyph; recolour via CSS mask
    rgba[:, :, 3] = alpha
    im = Image.fromarray(rgba, 'RGBA')
    if im.height > 256:
        w = int(im.width * 256 / im.height)
        im = im.resize((max(w, 1), 256), Image.LANCZOS)
    return im


# ---- output -----------------------------------------------------------------
CSS_HEAD = """/* GENERATED by tools/extract_icons.py — do not edit.

   Every icon is sized the way its own font glyph is: width, height and the
   baseline offset, in em. That is what makes a wide one (free) wide and a small
   one (unique) small, instead of squeezing them all into the same square.
   --icon-scale nudges them all together without disturbing their proportions. */
.ico{display:inline-block; background-color:var(--icon); margin:0 .06em;
  -webkit-mask-repeat:no-repeat; mask-repeat:no-repeat;
  -webkit-mask-position:center; mask-position:center;
  -webkit-mask-size:contain; mask-size:contain}
"""


def write_css(glyphs, symbols):
    lines = [CSS_HEAD]
    for name in sorted(glyphs):
        _svg, w, h, base = glyphs[name]
        lines.append(
            f'.ico-{name}{{width:calc({w:.3f}em*var(--icon-scale));'
            f'height:calc({h:.3f}em*var(--icon-scale));'
            f'vertical-align:calc({base:.3f}em*var(--icon-scale));'
            f'-webkit-mask-image:url(../assets/icons/{name}.svg);'
            f'mask-image:url(../assets/icons/{name}.svg)}}')
    for name, (w, h, base) in sorted(symbols.items()):
        lines.append(
            f'.ico-{name}{{width:calc({w:.3f}em*var(--icon-scale));'
            f'height:calc({h:.3f}em*var(--icon-scale));'
            f'vertical-align:calc({base:.3f}em*var(--icon-scale));'
            f'-webkit-mask-image:url(../assets/icons/{name}.png);'
            f'mask-image:url(../assets/icons/{name}.png)}}')
    with open(CSS_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'  {len(glyphs)+len(symbols)} rules -> css/icons.css')


def contact_sheet(names, outdir):
    """A quick visual check that nothing came out empty."""
    from PIL import ImageDraw
    cols = 6; rows = (len(names)+cols-1)//cols; cell = 120
    sheet = Image.new('RGBA', (cols*cell, rows*cell), (30, 34, 42, 255))
    d = ImageDraw.Draw(sheet)
    for i, nm in enumerate(names):
        d.text((i % cols*cell+6, i//cols*cell+cell-14), nm[:16], fill=(150, 160, 170, 255))
    sheet.save(os.path.join(outdir, '_contact_sheet.png'))


def build(pack, outdir=ICONS_DIR):
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pack.require_pdf())

    font_path = extract_font(doc, outdir)
    glyphs = {}
    if not font_path:
        print('  [warn] no Arkham icon font is embedded in this PDF; the font icons '
              'cannot be re-traced. Keeping the ones already in assets/icons/.')
    else:
        glyphs = trace_glyphs(font_path, glyph_ids(doc))
        for name, (svg, _w, _h, _b) in glyphs.items():
            with open(os.path.join(outdir, name + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(svg)
        os.remove(font_path)
        print(f'  {len(glyphs)} icons traced from the font -> assets/icons/*.svg')
        # Icons the Grimoire never prints (bless/curse) are traced from a FAQ font.
        fill_from_faq(glyphs, outdir)

    # symbols the font does not carry: clipped from the page as before
    symbols = {}
    for name, sm in pack.icon_art.get('symbols', {}).items():
        im = render_mask(doc[sm['page']-1], fitz.Rect(*sm['rect']), zoom=10, pad=1)
        if im is None:
            print('  [warn] symbol', name, 'came out empty')
            continue
        im.save(os.path.join(outdir, name + '.png'))
        # drawn art has no font metrics; size it like a capital letter
        h_em = 0.72
        symbols[name] = (h_em * im.width / im.height, h_em, -0.02)
        print(f'  symbol {name} -> assets/icons/{name}.png')

    if glyphs or symbols:
        write_css(glyphs, symbols)
        contact_sheet(sorted(list(glyphs) + list(symbols)), outdir)
    return glyphs


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    packs, _errs = langpack.load_valid()      # a broken pack must not stop the icons
    art = langpack.icon_art_pack(packs)
    if art is None:
        print('  [skip] no pack sets "iconArt": {"provides": true} — nothing to render.')
        return 0
    if not art.has_pdf():
        # The icons are committed, so a contributor who does not have the icon-art
        # PDF is fine: their language reuses the existing artwork.
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
