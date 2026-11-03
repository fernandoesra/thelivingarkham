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
# The same refraction frame WITHOUT the scenario diamond. The artist drew both, for the reason
# below — see frame_for().
FRAME_NOSET = {
    'ultimatum': 'Ultimatum-Refraction-NoSet.png',
    'boon': 'Boon-Refraction-NoSet.png',
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


def frame_for(cat, refraction, slug, refr):
    """Which frame goes over this card.

    A refraction that fixes ONE scenario prints that scenario's encounter-set symbol in a
    diamond above the type line. A refraction that applies to a WHOLE campaign has no scenario
    to name, and the artist drew a second frame with no diamond for exactly that case. Choosing
    on category alone left an empty diamond on the seven campaign-wide cards — a hole where the
    card is not supposed to have one at all.

    Which is which is not declared a second time: the same `set` in tools/ub_refractions.json
    that decides whether a scenario symbol is drawn on the subtitle decides this."""
    if not refraction:
        return FRAME.get((cat, False))
    if (refr.get(slug) or {}).get('set'):
        return FRAME.get((cat, True))
    return FRAME_NOSET.get(cat)


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
    # V1 (5argon's clean frame) art. The v2 "skin", the with-bleed exports and this card's backs
    # are regenerated offline — there is no committed builder for the cards-v2 / *-bleed / backs
    # dirs (they were added as binaries); the v2 source is Refraction_scorched_earth_fix_v2.png,
    # beside this file in the "Nuevos" folder.
    {'slug': 'ultimatum-of-scorched-earth', 'en': 'Ultimatum of Scorched Earth',
     'cat': 'ultimatum', 'refraction': True, 'file': 'Refraction_scorched_earth_fix_v1.png'},
]

# The fan-made "Cultist Challenges" cards (Week of Arkham Horror 2026); their rule text is
# injected by tools/ub_fanmade.py. Frame by role: three GENERAL ultimatums use the common
# frame; the five campaign-wide Children of Blood ultimatums use the refraction frame with
# NO scenario diamond; the three scenario-specific Children of Blood refractions use the
# diamond frame (its encounter-set symbol is drawn live by the app, once curated).
#
# `art` is the artist's full-bleed 1432x2000 PNG (no frame/text) in the "Nuevos/Fanmade"
# folder beside the main source; the frame is laid over it exactly like the main import, so
# the window shows the illustration. A card whose `art` file is absent falls back to a dark-
# ground placeholder, flagged noart, until its illustration arrives. Illustrators come from
# ub_illustrators.json like every other card.
FANMADE = [
    {'slug': 'ultimatum-of-maddening-truth', 'en': 'Ultimatum of Maddening Truth',
     'cat': 'ultimatum', 'refraction': False, 'frame': 'Ultimatum-Common.png',
     'art': '01-maddening-truth-by-Woodrow J. Hinton III.png'},
    {'slug': 'ultimatum-of-torment', 'en': 'Ultimatum of Torment',
     'cat': 'ultimatum', 'refraction': False, 'frame': 'Ultimatum-Common.png',
     'art': '02-torment-by-Ethan Patrick Harris.png'},
    {'slug': 'ultimatum-of-nihilism', 'en': 'Ultimatum of Nihilism',
     'cat': 'ultimatum', 'refraction': False, 'frame': 'Ultimatum-Common.png',
     'art': '03-Nihilism-by-Brian Valenzuela.png'},
    {'slug': 'ultimatum-of-thin-blood', 'en': 'Ultimatum of Thin Blood',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction-NoSet.png',
     'art': '04-Thin-blood-by-Peter Polach.png'},
    {'slug': 'ultimatum-of-regret', 'en': 'Ultimatum of Regret',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction-NoSet.png',
     'art': '05-Regret-by-Drazenka Kimpel.png'},
    {'slug': 'ultimatum-of-blood-frenzy', 'en': 'Ultimatum of Blood Frenzy (campaign)',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction-NoSet.png',
     'art': '06-blood-frenzy-campaing-by-Peter Polach.png'},
    {'slug': 'ultimatum-of-accursed-blood', 'en': 'Ultimatum of Accursed Blood',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction-NoSet.png',
     'art': '07-Accursed-blood-By-Brian Valenzuela.png'},
    {'slug': 'ultimatum-of-cold-blood', 'en': 'Ultimatum of Cold Blood',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction-NoSet.png',
     'art': '08-Cold-blood-by-Jeff Lee Johnson.png'},
    {'slug': 'ultimatum-of-hostility', 'en': 'Ultimatum of Hostility',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction.png',
     'art': '09-hostility-by-Andreia Ugrai.png'},
    {'slug': 'ultimatum-of-the-horde', 'en': 'Ultimatum of the Horde',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction.png',
     'art': '10-horde-by-Stella Spente.png'},
    {'slug': 'ultimatum-of-blood-frenzy-blood-money', 'en': 'Ultimatum of Blood Frenzy (scenario)',
     'cat': 'ultimatum', 'refraction': True, 'frame': 'Ultimatum-Refraction.png',
     'art': '11-frenzy-blood-money-by-Ethan Patrick.png'},
]


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
    refr = json.load(open(REFR, encoding='utf-8')) if os.path.exists(REFR) else {}

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
        slug = slugify(name)
        frame_name = frame_for(cat, refraction, slug, refr)
        if not frame_name or not os.path.exists(os.path.join(FRAMES, frame_name)):
            print(f'  skip (no frame for {cat}{"/refraction" if refraction else ""}): {fname}')
            continue
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
        kind = cat + (', refraction' if refraction else '')
        if refraction and frame_name in FRAME_NOSET.values():
            kind += ', campaign-wide (no scenario diamond)'
        print(f'  {slug}  {cw}x{ch}  ({kind})')

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

    # Fan-made cards. Each has the artist's full-bleed art (no frame/text) in nuevos/Fanmade;
    # the frame is laid over it so the window shows the illustration, exactly like the main
    # import. A card still lacking its art gets the frame over a dark ground, flagged noart, so
    # the viewer draws no illustrator line and shows an "illustration soon" hint until it lands.
    fanmade_dir = os.path.join(nuevos, 'Fanmade')
    for pl in FANMADE:
        if pl['slug'] in registry:
            continue
        if not os.path.exists(os.path.join(FRAMES, pl['frame'])):
            print(f'  skip fanmade (no frame): {pl["slug"]}')
            continue
        artpath = os.path.join(fanmade_dir, pl['art']) if pl.get('art') else None
        has_art = bool(artpath and os.path.exists(artpath))
        pic = framed(artpath, pl['frame']) if has_art else placeholder(pl['frame'])
        cw, ch = save_webp(pic, os.path.join(OUT, 'cards', pl['slug'] + '.webp'), args.width, 82)
        tw, th = save_webp(pic, os.path.join(OUT, 'thumbs', pl['slug'] + '.webp'), args.thumb, 80)
        rec = {
            'cat': pl['cat'], 'refraction': pl['refraction'], 'en': pl['en'],
            'card': f'ub/cards/{pl["slug"]}.webp', 'w': cw, 'h': ch,
            'thumb': f'ub/thumbs/{pl["slug"]}.webp', 'tw': tw, 'th': th,
        }
        if illus.get(pl['slug']):
            rec['illus'] = illus[pl['slug']]
        if not has_art:
            rec['noart'] = True
        registry[pl['slug']] = rec
        n += 1
        print(f'  {pl["slug"]}  {cw}x{ch}  ({"art" if has_art else "placeholder, no art"})')

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
