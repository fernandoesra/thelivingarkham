# -*- coding: utf-8 -*-
"""Objective fidelity check: verify each parsed entry's text actually appears in
the raw PDF text (letters-only, so hyphenation / line-wraps / icons don't matter).
Flags entries whose text was dropped or garbled. Reports overall coverage.

Usage:  python tools/validate_coverage.py <lang>
"""
import fitz, json, sys, re, unicodedata
import langpack
import text_fixes

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

def undo_fixes(s, rules):
    """Put back the wording the PDF actually prints, undoing our curated corrections.

    tools/text_fixes.json records, per language, every place we knowingly diverge from the
    book — a word its text layer split across a line break, or an outright typo in the official
    PDF ("el mazo de u jugador"). Comparing our corrected text against the PDF then reports a
    mismatch that IS the correction, which is the one mismatch that needs no eyeball.

    Only ever used as a fallback on a passage that already failed, and only believed when the
    result matches the PDF exactly — so a replacement that also occurs naturally elsewhere
    ("carta de Investigador") cannot corrupt a passage into a false pass."""
    for rule in rules:
        if rule.get('find') and rule.get('replace'):
            s = s.replace(rule['replace'], rule['find'])
    return s


def sentences(runs_blocks):
    """The passage cut into the pieces the page actually sets, as letters.

    A fixed-width window straddles the seams between them, which is why a re-ordered passage
    looks identical to a lost one under the sliding-window test — see reordered()."""
    out = []
    for b in runs_blocks:
        for r in b['runs']:
            if r['kind'] not in ('text', 'link'):
                continue
            for piece in re.split(r'(?<=[.:!?])\s+', r['t'] or ''):
                if len(letters(piece)) >= 12:
                    out.append(piece)
    return out


def reordered(blocks, doc, rules=()):
    """Whether every sentence of a passage IS in the PDF and only their ORDER differs.

    That is not a fidelity problem, it is us being right: a timing chart or a two-column list
    is read by COLUMN here, because read in the PDF's own stream order the columns interleave
    and the sentences shred. The chart's floating labels ("Player Window") then sit somewhere
    else entirely in that stream, so the assembled passage cannot appear in it as one run of
    letters however faithful it is — every phase-step chart in all four editions fails that way.

    Reported apart from real losses so a permanent false alarm cannot drown a true one."""
    sents = sentences(blocks)
    # Each sentence as we render it, or as the book prints it — a passage can be both re-ordered
    # and corrected. Undoing a correction is only ever ALLOWED, never forced: a replacement that
    # also occurs naturally ("Player card") would otherwise corrupt sentences that were already
    # right, which is exactly what happened when this undid them unconditionally.
    return bool(sents) and all(letters(s) in doc or letters(undo_fixes(s, rules)) in doc
                               for s in sents)


def report(pack, data):
    """Compare the assembled text against the raw PDF. Returns (checked, covered)."""
    lang = pack.code
    doc = raw_doc_letters(pack.require_pdf())
    total_units = covered = 0
    problems = []
    shuffled = []
    corrected = []
    rules = text_fixes.load().get(lang, [])
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
                elif letters(undo_fixes(entry_text(blocks), rules)) in doc:
                    covered += 1                       # the mismatch IS our own correction
                    corrected.append(name)
                elif reordered(blocks, doc, rules):
                    covered += 1                       # every sentence is there; only the order moved
                    shuffled.append(name)
                else:
                    problems.append((round(ratio, 2), name, len(txt)))
    pct = 100 * covered / max(checked, 1)
    print(f'  {checked} passages checked, {covered} found verbatim in {pack.current["pdf"]} '
          f'({pct:.1f}%)')
    if corrected:
        print(f'  {len(corrected)} passage(s) differ only by a correction we made on purpose '
              f'(tools/text_fixes.json): {", ".join(n[:28] for n in corrected[:3])}'
              f'{", …" if len(corrected) > 3 else ""}')
    if shuffled:
        print(f'  {len(shuffled)} passage(s) read by column — every sentence found, order differs '
              f'from the PDF stream (expected: {", ".join(n[:28] for n in shuffled[:3])}'
              f'{", …" if len(shuffled) > 3 else ""})')
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
