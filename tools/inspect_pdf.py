# -*- coding: utf-8 -*-
"""Look inside a Grimoire PDF so you can fill in your pack.

    python tools/inspect_pdf.py <lang|file.pdf> --sections
        Print the chapter headings the parser finds, and a ready-to-paste
        "sections" block for langs/<lang>/lang.json.

    python tools/inspect_pdf.py <lang|file.pdf> --grid 9
        Render page 9 with a labelled coordinate grid to
        assets/img/_inspect-p9.png, so you can read off the [x0, y0, x1, y1]
        of a montage region by eye.

    python tools/inspect_pdf.py <lang|file.pdf> --entries [N]
        Print the first N glossary-style headings, to sanity-check the parse.

The two jobs this answers are the only ones that genuinely need the PDF open:
naming your chapters, and measuring the picture regions.
"""
import json, os, sys
import fitz
import langpack
import parse_grimoire as P

GUESS_KINDS = {'glossary': 'glossary'}


def resolve(arg):
    """Accept either a language code or a path to a PDF.

    A code is resolved WITHOUT validating the pack: this tool is how you fill the
    pack in, so demanding a finished one would be a circle.
    """
    if os.path.exists(arg) and arg.lower().endswith('.pdf'):
        return None, arg
    return arg, langpack.peek_pdf(arg)


def sections(pack, pdf):
    lines, doc = P.collect_lines(pdf, {})
    heads = []
    for i, line in enumerate(lines):
        if P.line_is_heading(line) == 1:
            t = P.line_text(line)
            if t and t not in [h[1] for h in heads]:
                heads.append((line['page'], t))
    print(f'{len(heads)} chapter-level headings in {os.path.basename(pdf)}:\n')
    for page, t in heads:
        print(f'  p{page:>3}  {t}')

    # Only numbered chapters are suggested. Headings inside a chapter (the card
    # labels on the anatomy pages, say) use the same big type, so guessing which
    # of them is a chapter would produce confident nonsense.
    guessed = []
    known = list(langpack.SECTION_KEYS)
    for _page, t in heads:
        m = P.re.match(r'^\s*([IVXLC]+)\.\s*(.*)$', t)
        if not m:
            continue
        num, title = m.group(1), m.group(2).strip()
        key = known[len(guessed)] if len(guessed) < len(known) else 'CHOOSE-A-KEY'
        guessed.append({'num': num, 'key': key, 'id': langpack.slugify(title),
                        'title': title, 'kind': GUESS_KINDS.get(key, 'rules'),
                        'figures': []})
    print('\n' + '-' * 70)
    print('A starting point for "sections" in your lang.json — CHECK IT:')
    print('  · "key" is guessed purely from the order of the chapters.')
    print('  · "kind" is "rules" for everything except the glossary. Use "figures"')
    print('    for the picture-only chapters (card anatomy, icon tables, quick reference).')
    print('  · Only numbered chapters ("I.", "II.", …) are listed. If your book ends')
    print('    with an unnumbered sheet, add it by hand with "num": "".')
    print(f'  · Valid keys: {", ".join(langpack.SECTION_KEYS)}')
    print('-' * 70)
    print(json.dumps({'sections': guessed}, ensure_ascii=False, indent=2))


def entries(pack, pdf, limit=20):
    lines, doc = P.collect_lines(pdf, {})
    n = 0
    for line in lines:
        if P.line_is_heading(line) == 3:
            print(f'  p{line["page"]:>3}  {P.line_text(line)}')
            n += 1
            if n >= limit:
                break
    print(f'\n({n} entry headings shown — these become the glossary entries)')


def grid(pack, pdf, page_no, outdir=None):
    """Render one page with a 50pt coordinate grid, to measure montage clips."""
    doc = fitz.open(pdf)
    if not (1 <= page_no <= doc.page_count):
        raise langpack.PackError(f'{os.path.basename(pdf)} has {doc.page_count} pages; '
                                 f'there is no page {page_no}.')
    page = doc[page_no - 1]
    zoom = 2.0
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    outdir = outdir or os.path.join(langpack.ROOT, 'assets', 'img')
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f'_inspect-p{page_no}.png')

    from PIL import Image, ImageDraw
    im = Image.frombytes('RGB', (pm.w, pm.h), pm.samples).convert('RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    r = page.rect
    step = 50
    for x in range(0, int(r.width) + step, step):
        d.line([(x * zoom, 0), (x * zoom, im.height)], fill=(255, 0, 0, 90), width=1)
        d.text((x * zoom + 2, 2), str(x), fill=(255, 0, 0, 255))
    for y in range(0, int(r.height) + step, step):
        d.line([(0, y * zoom), (im.width, y * zoom)], fill=(255, 0, 0, 90), width=1)
        d.text((2, y * zoom + 2), str(y), fill=(255, 0, 0, 255))
    im.save(out)
    print(f'page {page_no} of {os.path.basename(pdf)} is {r.width:.0f} x {r.height:.0f} points')
    print(f'grid (every {step} pt) -> {os.path.relpath(out, langpack.ROOT)}')
    print('\nRead the corners of the picture off the red grid, then write them as')
    print('  "clip": [x0, y0, x1, y1]     (x from the left, y from the TOP)')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    pack, pdf = resolve(argv[0])
    rest = argv[1:]
    if '--grid' in rest:
        i = rest.index('--grid')
        if i + 1 >= len(rest):
            print('--grid needs a page number, e.g. --grid 9', file=sys.stderr)
            return 2
        grid(pack, pdf, int(rest[i + 1]))
    elif '--entries' in rest:
        i = rest.index('--entries')
        n = int(rest[i + 1]) if i + 1 < len(rest) and rest[i + 1].isdigit() else 20
        entries(pack, pdf, n)
    else:
        sections(pack, pdf)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
