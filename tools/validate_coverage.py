# -*- coding: utf-8 -*-
"""Objective fidelity check: verify each parsed entry's text actually appears in
the raw PDF text (letters-only, so hyphenation / line-wraps / icons don't matter).
Flags entries whose text was dropped or garbled. Reports overall coverage.

Usage:  python tools/validate_coverage.py <lang>
"""
import fitz, json, sys, re, unicodedata
import langpack

def letters(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

def raw_doc_letters(pdf):
    d = fitz.open(pdf)
    return letters(''.join(p.get_text('text') for p in d))

def entry_text(runs_blocks):
    # runs_blocks: list of blocks with runs; use ONLY text/link runs (skip icons)
    out = []
    for b in runs_blocks:
        for r in b['runs']:
            if r['kind'] in ('text', 'link'):
                out.append(r['t'])
    return ' '.join(out)

def report(pack, data):
    """Compare the assembled text against the raw PDF. Returns (checked, covered)."""
    lang = pack.code
    doc = raw_doc_letters(pack.require_pdf())
    total_units = covered = 0
    problems = []
    checked = 0
    for s in data['sections']:
        blocks_groups = []
        if s.get('intro'):
            blocks_groups.append(('[intro] ' + s['title'], s['intro']))
        for e in s.get('entries', []):
            blocks_groups.append((e['title'], e['blocks']))
        for name, blocks in blocks_groups:
            txt = letters(entry_text(blocks))
            if len(txt) < 12:
                continue
            checked += 1
            total_units += 1
            if txt in doc:
                covered += 1
            else:
                # measure best coverage via sliding chunks (30-char windows)
                win = 40
                hit = sum(1 for i in range(0, max(1, len(txt)-win), win) if txt[i:i+win] in doc)
                tries = max(1, len(range(0, max(1, len(txt)-win), win)))
                ratio = hit/tries
                if ratio >= 0.92:
                    covered += 1
                else:
                    problems.append((round(ratio, 2), name, len(txt)))
    pct = 100 * covered / max(checked, 1)
    print(f'  {checked} passages checked, {covered} found verbatim in {pack.current["pdf"]} '
          f'({pct:.1f}%)')
    if problems:
        problems.sort()
        # Not a failure: a passage stitched together across columns or pages can
        # read perfectly and still not appear as one run of letters in the PDF.
        # What matters is the shape — a healthy pack sits in the high 80s/90s; a
        # near-zero score means the parser and the book disagree about the text.
        print(f'  {len(problems)} passage(s) matched below 92% — worth an eyeball:')
        for ratio, name, n in problems[:5]:
            print(f'    {ratio:.0%}  {name[:50]!r}')
        if len(problems) > 5:
            print(f'    … {len(problems)-5} more (python tools/validate_coverage.py {lang})')
    if pct < 50:
        print(f'  [warn] only {pct:.0f}% of the text was found in the PDF. Something is wrong: '
              f'check that "book.versions" points at the right file.')
    return checked, covered


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/validate_coverage.py <lang>', file=sys.stderr)
        return 2
    pack = langpack.load(sys.argv[1])
    data = json.load(open(pack.data_path, encoding='utf-8'))
    report(pack, data)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
