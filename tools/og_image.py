#!/usr/bin/env python3
"""The share image: what a link to the site shows on WhatsApp, Discord, Telegram, X, Facebook.

    python tools/og_image.py      -> assets/og-image.jpg (1200x630)

1200x630 is the size every network crops to. It is the landing page's hero (the banner art,
signed by its illustrator exactly as the hero signs it) under the site's name. It carries no
language: one image serves every page, and tools/seo.py points every og:image at it. Re-run
only if the banner, the name or the fonts change.
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
W, H = 1200, 630
BANNER = ROOT / 'assets/general_banner_01.webp'
# The sigil is the header's own vector mark (index.html, svg.tla-sigil): one M…L…Z polygon
# in a 100x100 box, so it is drawn here directly, in the brand's gold, at any size.
SIGIL_SRC = ROOT / 'index.html'
TITLE_FONT = ROOT / 'assets/fonts/Teutonic.ttf'
BODY_FONT = ROOT / 'assets/fonts/arnopro-regular.otf'
ITALIC_FONT = ROOT / 'assets/fonts/arnopro-italic.otf'
OUT = ROOT / 'assets/og-image.jpg'   # JPEG: WhatsApp drops previews much over ~300 KB

# The same credit the landing hero prints (js/app.js HERO_ART); the word is the card credits'.
CREDIT = 'Illus. Aurore Folny'
NAME = 'The Living Arkham'
SUB = 'Arkham Horror: The Card Game'
INK = (226, 231, 240)        # midnight theme --ink
GOLD = (203, 174, 116)       # slate theme --gold2, the brand's own gold


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def sigil(size, fill):
    d = re.search(r'<svg class="tla-sigil"[^>]*><path d="([^"]+)"', SIGIL_SRC.read_text(encoding='utf-8')).group(1)
    pts = [(float(x), float(y)) for x, y in re.findall(r'[ML]\s*([\d.]+)[ ,]([\d.]+)', d)]
    k = 4                                    # drawn 4x and scaled down: an antialiased edge
    m = Image.new('L', (size * k, size * k), 0)
    ImageDraw.Draw(m).polygon([(x * size * k / 100, y * size * k / 100) for x, y in pts], fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    out = Image.new('RGBA', (size, size), fill + (0,))
    out.putalpha(m)
    return out


def centered(draw, y, text, font, fill, shadow=True):
    w = draw.textlength(text, font=font)
    x = (W - w) / 2
    if shadow:
        for dx, dy in ((0, 3), (2, 2), (-2, 2)):
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=fill)


def main():
    bg = cover(Image.open(BANNER).convert('RGB'), W, H)
    # Darken toward the bottom, where the name sits, so it reads over a busy painting.
    shade = Image.new('L', (W, H))
    px = shade.load()
    for y in range(H):
        a = int(255 * min(1.0, max(0.0, (y - H * 0.25) / (H * 0.6))) ** 1.3 * 0.86) + 40
        for x in range(W):
            px[x, y] = min(255, a)
    dark = Image.new('RGB', (W, H), (14, 16, 22))
    img = Image.composite(dark, bg, shade).convert('RGBA')

    sig = sigil(150, GOLD)
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 230), ((W - 150) // 2, 236 + 4), sig)
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(8)))
    img.paste(sig, ((W - 150) // 2, 236), sig)

    d = ImageDraw.Draw(img)
    centered(d, 392, NAME, ImageFont.truetype(str(TITLE_FONT), 92), INK)
    centered(d, 508, SUB, ImageFont.truetype(str(BODY_FONT), 40), GOLD)
    cf = ImageFont.truetype(str(ITALIC_FONT), 22)
    d.text((W - 24 - d.textlength(CREDIT, font=cf), H - 40), CREDIT, font=cf, fill=(200, 205, 214))
    img.convert('RGB').save(OUT, quality=86, optimize=True, progressive=True)
    print(f'og_image: {OUT.relative_to(ROOT).as_posix()} ({W}x{H}, {OUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
