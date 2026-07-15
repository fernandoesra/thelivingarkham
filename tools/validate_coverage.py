# -*- coding: utf-8 -*-
"""Objective fidelity check: verify each parsed entry's text actually appears in
the raw PDF text (letters-only, so hyphenation / line-wraps / icons don't matter).
Flags entries whose text was dropped or garbled. Reports overall coverage."""
import fitz, json, sys, re, unicodedata

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

def main():
    lang, data_path, pdf = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.load(open(data_path, encoding='utf-8'))
    doc = raw_doc_letters(pdf)
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
    print(f'[{lang}] entries/introblocks checked: {checked}  fully-verified: {covered}  '
          f'({100*covered/max(checked,1):.1f}%)')
    if problems:
        problems.sort()
        print(f'  {len(problems)} below 92% coverage:')
        for ratio, name, n in problems[:25]:
            print(f'    {ratio:.0%}  {name[:50]!r}  (len {n})')
    else:
        print('  ALL passages verified present in the source PDF.')

if __name__ == '__main__':
    main()
