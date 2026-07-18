# -*- coding: utf-8 -*-
"""Build the Ultimatums & Boons card pictures for the site — art only, no text.

The site renders each card's TEXT live, in the reader's language, over a fixed
picture. So the picture must carry the illustration and 5argon's frame but NOT
the printed English title and rule. This makes that picture: it lays the frame
(assets/templates/.../frames, its centre transparent, its title/type/text bands
opaque) over the full rendered card, which hides the baked English text and
leaves the art showing through the window. Then it crops the print bleed and
re-encodes small as WebP — ~760 px for the detail card, a thumbnail for the list.

Two source folders (a Google Drive mount the artist publishes, outside the repo):
  Cards-V2/       full rendered fronts WITH bleed  (1432x2000, ~2.8 MB each)
  ...and the frames are the local copies under assets/templates.

The frame and the with-bleed card share an aspect ratio, so the frame is resized
to the card and composited 1:1; the no-bleed crop is the same centre crop the
artist's own no-bleed export uses. Output: assets/ub/<cards|thumbs>/<slug>.webp
plus assets/ub/index.json, a language-neutral registry keyed by a slug from the
English card name. Nothing here knows any language.

Refractions belong to past campaigns and come in on request (--refractions).

Usage:
  python tools/import_ub_cards.py [--src DIR] [--refractions] [--width N] [--thumb N]
"""
import argparse, json, os, re, sys, unicodedata
from PIL import Image

Image.MAX_IMAGE_PIXELS = None            # the frames are big by design, not a bomb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'ub')
FRAMES = os.path.join(ROOT, 'assets', 'templates', 'ultimatums_boons', 'frames')
# Curated slug -> illustrator, read off the printed cards (bottom-left "Illus. X").
# Language-neutral, so it lives here and the site renders it under a localized "Illus."
ILLUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ub_illustrators.json')
# Curated slug -> {set, collection} icon codes for refractions (their encounter set and
# product symbols, drawn on the subtitle). Also language-neutral.
REFR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ub_refractions.json')
DEFAULT_SRC = ('C:/Users/Fernando/Mi unidad/Rincon Miskatonic/Contenido AH LCG/'
               'Ultimatums and Boons/Ingles original')
CARDS_SUB = 'Cards-V2'                    # WITH bleed, to match the frame's bleed

# The frame that hides the text and rims the art, by (category, is-refraction).
FRAME = {
    ('ultimatum', False): 'Ultimatum-Common.png',
    ('boon', False): 'Boon-Common.png',
    ('ultimatum', True): 'Ultimatum-Refraction.png',
    ('boon', True): 'Boon-Refraction.png',
}
# Centre crop that turns the bleed card into the no-bleed one (60/1432, 91/2000):
# the artist's own no-bleed export is this exact crop (verified pixel-identical).
BLEED_X, BLEED_Y = 60 / 1432, 91 / 2000


def slugify(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()


def parse(fname):
    """('Ultimatum of Chaos', 'ultimatum', False) from a front-image filename."""
    base = fname[:-len('-A.png')]
    refraction = base.startswith('Refraction-')
    if refraction:
        base = base[len('Refraction-'):]
    if base.startswith('Ultimatum'):
        cat = 'ultimatum'
    elif base.startswith('Boon'):
        cat = 'boon'
    else:
        cat = None
    return base, cat, refraction


_frame_cache = {}


def _frame(frame_name, size):
    key = (frame_name, size)
    fr = _frame_cache.get(key)
    if fr is None:
        fr = Image.open(os.path.join(FRAMES, frame_name)).convert('RGBA').resize(
            size, Image.LANCZOS)
        _frame_cache[key] = fr
    return fr


def _crop_bleed(comp):
    W, H = comp.size
    dx, dy = round(W * BLEED_X), round(H * BLEED_Y)
    return comp.crop((dx, dy, W - dx, H - dy))


def framed(card_path, frame_name):
    """The card with the frame over it (text hidden), bleed cropped, RGBA."""
    card = Image.open(card_path).convert('RGBA')
    comp = Image.alpha_composite(card, _frame(frame_name, card.size))
    return _crop_bleed(comp)


# A card the manual names but has no fan art yet: the frame over a plain dark ground,
# so the viewer shows it (title + rule, rendered live) with an empty art window until
# the illustration arrives. Standard bleed size, so the same crop applies.
PLACEHOLDER_SIZE = (1432, 2000)
PLACEHOLDER_BG = (14, 14, 18, 255)


def placeholder(frame_name):
    bg = Image.new('RGBA', PLACEHOLDER_SIZE, PLACEHOLDER_BG)
    return _crop_bleed(Image.alpha_composite(bg, _frame(frame_name, PLACEHOLDER_SIZE)))


def pre_framed(path):
    """An artist's own finished composite — frame already applied, no text. Bleed-crop only,
    so nothing is drawn over the art a second time."""
    return _crop_bleed(Image.open(path).convert('RGBA'))


# Finished cards whose art lives outside the main export (an artist's own composite in the
# "Nuevos" folder beside the source). `file` is that composite; it is bleed-cropped as is.
EXTRA = [
    {'slug': 'ultimatum-of-scorched-earth', 'en': 'Ultimatum of Scorched Earth',
     'cat': 'ultimatum', 'refraction': True, 'file': 'Refraction_scorched_earth.png'},
]

# Cards the Grimoire names but with no art anywhere yet — rendered from the frame alone.
PLACEHOLDERS = []


def save_webp(im, dst, width, quality):
    h = round(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS).convert('RGB')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst, 'WEBP', quality=quality, method=6)
    return width, h


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=DEFAULT_SRC, help='the "Ingles original" folder')
    ap.add_argument('--refractions', action='store_true',
                    help='also import the past-campaign Refraction cards')
    ap.add_argument('--width', type=int, default=760, help='detail image width')
    ap.add_argument('--thumb', type=int, default=132, help='thumbnail width')
    args = ap.parse_args()

    cards_dir = os.path.join(args.src, CARDS_SUB)
    if not os.path.isdir(cards_dir):
        print(f'ERROR: card source not found: {cards_dir}', file=sys.stderr)
        return 1
    if not os.path.isdir(FRAMES):
        print(f'ERROR: frames not found: {FRAMES}\n'
              f'  (they live under assets/templates, kept out of git for size)',
              file=sys.stderr)
        return 1

    illus = json.load(open(ILLUS, encoding='utf-8')) if os.path.exists(ILLUS) else {}

    fronts = sorted(f for f in os.listdir(cards_dir) if f.endswith('-A.png'))
    registry = {}
    seen = {}
    n = 0
    for fname in fronts:
        name, cat, refraction = parse(fname)
        if cat is None:
            print(f'  skip (unknown type): {fname}')
            continue
        if refraction and not args.refractions:
            continue
        frame_name = FRAME.get((cat, refraction))
        if not frame_name or not os.path.exists(os.path.join(FRAMES, frame_name)):
            print(f'  skip (no frame for {cat}{"/refraction" if refraction else ""}): {fname}')
            continue
        slug = slugify(name)
        if slug in seen:
            raise SystemExit(f'slug collision {slug!r}: {seen[slug]} vs {fname}')
        seen[slug] = fname

        pic = framed(os.path.join(cards_dir, fname), frame_name)
        cw, ch = save_webp(pic, os.path.join(OUT, 'cards', slug + '.webp'), args.width, 82)
        tw, th = save_webp(pic, os.path.join(OUT, 'thumbs', slug + '.webp'), args.thumb, 80)
        registry[slug] = {
            'cat': cat, 'refraction': refraction, 'en': name,
            'card': f'ub/cards/{slug}.webp', 'w': cw, 'h': ch,
            'thumb': f'ub/thumbs/{slug}.webp', 'tw': tw, 'th': th,
        }
        if illus.get(slug):
            registry[slug]['illus'] = illus[slug]
        n += 1
        print(f'  {slug}  {cw}x{ch}  ({cat}{", refraction" if refraction else ""})')

    # Finished cards whose art the artist composited themselves (the "Nuevos" folder).
    nuevos = os.path.join(os.path.dirname(args.src), 'Nuevos')
    for ex in EXTRA:
        path = os.path.join(nuevos, ex['file'])
        if not os.path.exists(path):
            print(f'  skip extra (image not found: {path})')
            continue
        pic = pre_framed(path)
        cw, ch = save_webp(pic, os.path.join(OUT, 'cards', ex['slug'] + '.webp'), args.width, 82)
        tw, th = save_webp(pic, os.path.join(OUT, 'thumbs', ex['slug'] + '.webp'), args.thumb, 80)
        registry[ex['slug']] = {
            'cat': ex['cat'], 'refraction': ex['refraction'], 'en': ex['en'],
            'card': f'ub/cards/{ex["slug"]}.webp', 'w': cw, 'h': ch,
            'thumb': f'ub/thumbs/{ex["slug"]}.webp', 'tw': tw, 'th': th,
        }
        if illus.get(ex['slug']):
            registry[ex['slug']]['illus'] = illus[ex['slug']]
        n += 1
        print(f'  {ex["slug"]}  {cw}x{ch}  (finished art, {ex["cat"]}{", refraction" if ex["refraction"] else ""})')

    # Art-less cards the manual lists: the frame over a dark ground, marked noart so the
    # viewer knows there is no illustrator line to draw and shows an "illustration soon" hint.
    for pl in PLACEHOLDERS:
        if pl['slug'] in registry:
            continue
        if not os.path.exists(os.path.join(FRAMES, pl['frame'])):
            print(f'  skip placeholder (no frame): {pl["slug"]}')
            continue
        pic = placeholder(pl['frame'])
        cw, ch = save_webp(pic, os.path.join(OUT, 'cards', pl['slug'] + '.webp'), args.width, 82)
        tw, th = save_webp(pic, os.path.join(OUT, 'thumbs', pl['slug'] + '.webp'), args.thumb, 80)
        registry[pl['slug']] = {
            'cat': pl['cat'], 'refraction': pl['refraction'], 'en': pl['en'], 'noart': True,
            'card': f'ub/cards/{pl["slug"]}.webp', 'w': cw, 'h': ch,
            'thumb': f'ub/thumbs/{pl["slug"]}.webp', 'tw': tw, 'th': th,
        }
        n += 1
        print(f'  {pl["slug"]}  {cw}x{ch}  (placeholder, no art)')

    # Refraction subtitle symbols (encounter set + collection), applied by slug.
    refr = json.load(open(REFR, encoding='utf-8')) if os.path.exists(REFR) else {}
    for slug, meta in refr.items():
        if slug.startswith('_') or slug not in registry:
            continue
        if meta.get('set'):
            registry[slug]['set'] = meta['set']
        if meta.get('collection'):
            registry[slug]['collection'] = meta['collection']

    order = {'ultimatum': 0, 'boon': 1}
    registry = dict(sorted(registry.items(),
                           key=lambda kv: (kv[1]['refraction'],
                                           order[kv[1]['cat']], kv[1]['en'])))
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as fh:
        json.dump({'cards': registry}, fh, ensure_ascii=False, indent=1)
    print(f'\n  {n} card(s) -> assets/ub/  (textless, framed; index.json)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
