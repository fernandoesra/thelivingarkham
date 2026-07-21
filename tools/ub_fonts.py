# -*- coding: utf-8 -*-
"""Cut the Ultimatums & Boons web fonts from the print masters.

The card viewer draws its cards with two faces: a display face for the title and a text face,
in four styles, for everything else. Both are large print fonts, so the site ships SUBSETS —
assets/fonts/ub/*.woff2, a few hundred glyphs each instead of a thousand.

Those subsets were cut once, by hand, and that turned out to be a trap in two ways. They cannot
be reproduced (nothing in the repo knew how they were made), and they were cut against the
languages that existed at the time: German writes an opening quote as U+201E („), no shipped
face had it, and thirteen German cards were falling back to a system font — which changes the
metrics the card's own text-fitting depends on, so the text overflowed the card (deploy.md
names that exact symptom).

So the character set is not written down here either: it is READ from the built corpora, from
the very fields the card renderer draws (js/app.js ubDetailHTML — the title, the subtitle, the
type line, the rule text and the illustrator credit), across every language that has a book.
Add a language, run this, and its letters are in the fonts. Nothing to maintain by hand.

The masters live in assets/fonts/ (arnopro-*.otf, Teutonic.ttf) and are committed for exactly
this reason: they are build inputs, not reference copies.

Usage:  python tools/ub_fonts.py            # rebuild the subsets
        python tools/ub_fonts.py --check    # report coverage, write nothing
"""
import glob
import json
import os
import sys

import langpack

FONTS = os.path.join(langpack.ROOT, 'assets', 'fonts')
OUT = os.path.join(FONTS, 'ub')

# subset file -> master. The four text styles are one family in four faces; the title face is
# its own. Keep this table beside the @font-face block in css/app.css.
FACES = {
    'ub-title.woff2': 'Teutonic.ttf',
    'ub-body.woff2': 'arnopro-regular.otf',
    'ub-body-b.woff2': 'arnopro-bold.otf',
    'ub-body-i.woff2': 'arnopro-italic.otf',
    'ub-body-bi.woff2': 'arnopro-bolditalic.otf',
}

# Always included, whatever the corpora happen to contain today: the ASCII range the interface
# itself needs, and the punctuation a translator reaches for. A subset that fits the current
# text exactly would break on the next card that adds a dash.
BASE = (''.join(chr(c) for c in range(0x20, 0x7F))
        # The invisible ones, kept deliberately: a no-break space is what French typography puts
        # before a colon and what a translator's editor inserts without anyone seeing it, and a
        # soft hyphen is how a long compound is allowed to break. Missing, they are the hardest
        # kind of fallback to notice — a single character in another face, mid-word.
        + ' ­ ‑'
        + '¡¿€…–—‘’‚“”„«»†‡•·°×÷©®™'
        + 'ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝß'
        + 'àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ'
        + 'ĀāĂăĄąĆćČčĎďĐđĒēĖėĘęĚěĞğĪīĮįŁłŃńŇňŌōŐőŒœŔŕŘřŚśŞşŠšŤťŪūŮůŰűŲųŸŹźŻżŽž')


def _runs_text(blocks):
    out = []
    for b in blocks or []:
        for r in b.get('runs') or []:
            if r.get('kind') in ('text', 'link', 'adbcard', 'flowref'):
                out.append(r.get('t') or '')
    return out


def wanted():
    """(every character the viewer can draw, the ones actually PRINTED on a card, cards seen).

    The two sets are kept apart on purpose. The first is what to cut — padded with BASE so the
    next card that uses a dash does not need a new subset. The second is what to COMPLAIN about:
    a master that cannot draw a padding character is unremarkable, while a master that cannot
    draw a character a real card prints is a card that will render in a fallback face."""
    used = set()
    seen = 0
    for path in sorted(glob.glob(os.path.join(langpack.DATA_DIR, 'grimoire_*.json'))):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for s in data.get('sections') or []:
            ub = s.get('ub') or {}
            for bucket in ('ultimatums', 'boons', 'refractions'):
                for it in ub.get(bucket) or []:
                    seen += 1
                    used.update(it.get('name') or '')
                    used.update(it.get('illus') or '')
                    for t in _runs_text(it.get('blocks')):
                        used.update(t)
                    for r in it.get('subtitle') or []:
                        used.update(r.get('t') or '')
    # …plus the interface words printed on the card itself (the type line, "Illus.").
    for pack in langpack.load_valid()[0]:
        st = (pack.ui or {}).get('strings') or {}
        for key in ('ubtypeultimatum', 'ubtypeboon', 'ubtyperefraction', 'ubillus',
                    'refrcampaign'):
            used.update(st.get(key) or '')
    return set(BASE) | used, used, seen


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    check = '--check' in sys.argv[1:]
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        print('This needs fonttools (and brotli for woff2):\n  pip install fonttools brotli',
              file=sys.stderr)
        return 1

    chars, used, cards = wanted()
    print(f'  {len(chars)} character(s) to cut ({len(used)} of them printed on a real card), '
          f'read from {cards} card record(s)')
    os.makedirs(OUT, exist_ok=True)
    missing_any = 0
    for name, master_name in FACES.items():
        master = os.path.join(FONTS, master_name)
        if not os.path.exists(master):
            print(f'  [warn] master missing, {name} left as it is: {master_name}\n'
                  f'         (the print masters live in assets/fonts/ — see the README there)',
                  file=sys.stderr)
            continue
        have = set(TTFont(master).getBestCmap())
        # Only a character a card really prints is worth reporting: the master not covering a
        # padding letter costs nothing, the master not covering printed text is a fallback face
        # on a real card, and the card's text fitting is measured in the face it expects.
        gone = sorted(c for c in used if ord(c) not in have)
        if gone:
            missing_any += 1
            print(f'  [warn] {master_name} cannot draw {len(gone)} printed character(s): '
                  f'{"".join(gone[:24])}\n'
                  f'         those cards fall back to a system face (see deploy.md).',
                  file=sys.stderr)
        keep = ''.join(c for c in sorted(chars) if ord(c) in have)
        dst = os.path.join(OUT, name)
        if check:
            cur = set(TTFont(dst).getBestCmap()) if os.path.exists(dst) else set()
            short = sorted(c for c in keep if ord(c) not in cur)
            print(f'  {name:16} has {len(cur):4} glyph(s); {len(short)} still missing'
                  + (f' -> {"".join(short[:20])}' if short else ''))
            continue
        args = [master, f'--text={keep}', '--flavor=woff2', f'--output-file={dst}',
                '--layout-features=*', '--no-hinting', '--desubroutinize']
        subset.main(args)
        print(f'  {name:16} <- {master_name:24} {len(TTFont(dst).getBestCmap())} glyph(s), '
              f'{os.path.getsize(dst):,} B')
    return 1 if (missing_any and not check) else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
