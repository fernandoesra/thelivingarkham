# -*- coding: utf-8 -*-
"""
Deterministic parser: Arkham Grimoire PDF  ->  structured JSON.

Design goals:
  * 100% faithful to the source rules text (no paraphrasing).
  * Column-aware reading order (2-column US-Letter layout).
  * Span-level heading detection using the embedded fonts:
        Teutonic* >=17.5  -> section / big heading  (h1)
        Teutonic* 15.5-17.5 -> subsection           (h2)
        Teutonic* 13.0-15.5 -> glossary entry / item (h3)
  * Body text -> paragraphs & bullets with inline runs
        (bold / italic / game-icon / cross-reference).

Usage:  python tools/parse_grimoire.py <lang>
The PDF to read, and the montage regions to mask out of it, both come from that
language's pack (langs/<lang>/lang.json).
"""
import fitz, json, re, sys, os, unicodedata
import langpack
from icons import ICON_MAP, is_icon_font

TEAL = 0x306360           # cross-reference colour
# illustration credits from embedded example cards (not rules prose)
CREDIT = re.compile(r'(Illus\.|©\s*20\d\d\b.*FFG|Pixoloid\s+Studios)', re.I)
PAGE_MID = 306            # column split for a 612pt-wide page
FOOT_Y = 748              # ignore footer page numbers below this

def is_head_font(font):   # any Teutonic variant is a heading face
    return 'Teutonic' in font
def is_bullet_font(font):
    return 'Bodoni' in font or 'Ornament' in font

def is_new_red(s):
    """True for the dark-red text that marks content added in this version.
    Excludes the icon font and the big 'STOP!' callout heading (also reddish)."""
    if is_icon_font(s['font']):
        return False
    if is_head_font(s['font']) and s['size'] >= 15.5:
        return False
    c = s.get('color', 0)
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return r >= 0x80 and g <= 0x40 and b <= 0x40 and (r - g) >= 0x40

def span_kind(s):
    f, sz = s['font'], s['size']
    # 22+ = cover title (38), card-diagram callout numbers (31.2), em-dash (24.4): not headings
    if is_head_font(f) and 13.0 <= sz < 22.0:
        if sz >= 17.5: return ('H', 1)
        if sz >= 15.5: return ('H', 2)
        return ('H', 3)
    return ('B', 0)

def norm(t):
    return re.sub(r'\s+', ' ', t).strip()

def slugify(t):
    t = t.strip().lower()
    t = t.replace('“','').replace('”','').replace('"','').replace('’',"'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t or 'x'

def masks_for(pack):
    """{page(1-idx): [(x0,y0,x1,y1), ...]} of this pack's montage regions, used to
    drop card text that is shown as a figure instead of as body prose.

    The coordinates were measured against one specific PDF, so they are only
    valid for the newest version's file — see `check_montage_coords`.
    """
    res = {}
    for m in pack.montages:
        res.setdefault(m['page'], []).append(tuple(m['clip']))
    return res


def collect_lines(pdf, masks):
    """Return list of logical lines in reading order across the doc.
    Each line: {page, col, y, x0, spans:[...]} where a span keeps font/size/color/text."""
    doc = fitz.open(pdf)
    out = []
    gblock = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        page_masks = masks.get(pno + 1, [])
        blocks = [b for b in page.get_text('dict')['blocks'] if b['type'] == 0]
        edges = column_edges(blocks)              # dynamic: handles 1..N column spreads
        raw = []
        for b in blocks:
            gblock += 1
            bid = gblock
            for l in b['lines']:
                spans = [s for s in l['spans'] if s['text'] != '']
                if not spans:
                    continue
                x0 = min(s['bbox'][0] for s in spans)
                x1 = max(s['bbox'][2] for s in spans)
                y0 = min(s['bbox'][1] for s in spans)
                y1 = max(s['bbox'][3] for s in spans)
                if y0 >= FOOT_Y:            # footer page number
                    continue
                if page_masks:             # drop card text overlaid on a montage
                    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                    if any(mx0 <= cx <= mx1 and my0 <= cy <= my1
                           for (mx0, my0, mx1, my1) in page_masks):
                        continue
                col, xedge = col_of(x0, edges)
                raw.append({'page': pno+1, 'col': col, 'xedge': xedge, 'y': y0, 'y1': y1,
                            'x0': x0, 'spans': spans, 'block': bid})
        # reading order: column (left->right, incl. 2-up spreads) then vertical
        raw.sort(key=lambda r: (r['col'], round(r['y']), r['x0']))
        out.extend(raw)
    return out, doc


def column_edges(blocks):
    """Detect column left-edges by clustering block x0 values (gutter > ~160pt)."""
    xs = sorted(min(s['bbox'][0] for l in b['lines'] for s in l['spans'] if s['text'].strip())
                for b in blocks if any(s['text'].strip() for l in b['lines'] for s in l['spans']))
    if not xs:
        return [0.0]
    edges = [xs[0]]
    for x in xs[1:]:
        if x - edges[-1] > 160:
            edges.append(x)
    return edges


def col_of(x0, edges):
    """Return (column index, that column's left edge) for a line starting at x0."""
    idx = 0
    for i, e in enumerate(edges):
        if x0 + 8 >= e:
            idx = i
    return idx, edges[idx]

def line_text(line):
    return norm(''.join(s['text'] for s in line['spans']))

def line_is_heading(line):
    """A heading line: dominated by Teutonic heading spans (ignoring whitespace)."""
    hchars = bchars = 0
    lvl = 9
    for s in line['spans']:
        k, l = span_kind(s)
        n = len(s['text'].strip())
        if n == 0:
            continue
        if k == 'H':
            hchars += n
            lvl = min(lvl, l)
        else:
            bchars += n
    if hchars == 0:
        return None
    if hchars >= bchars:          # mostly heading
        return lvl
    return None

def build_runs(spans):
    """Turn a list of spans into inline runs, merging adjacent text of same style."""
    runs = []
    def push(kind, **kw):
        runs.append(dict(kind=kind, **kw))
    for s in spans:
        f = s['font']; txt = s['text']
        if is_icon_font(f):
            for ch in txt:
                cp = ord(ch)
                if cp in ICON_MAP:
                    push('icon', name=ICON_MAP[cp])
                elif ch.strip():
                    push('icon', name='unknown', cp='U+%04X' % cp)
            continue
        if is_bullet_font(f):
            continue  # bullet marker handled by caller
        bold = 'Bold' in f or 'Smbd' in f or 'Semibold' in f
        italic = 'Italic' in f or '-It' in f
        ref = (s.get('color', 0) == TEAL)
        red = is_new_red(s)
        # merge with previous compatible text run
        if runs and runs[-1]['kind'] == 'text' and runs[-1]['bold'] == bold \
                and runs[-1]['italic'] == italic and runs[-1]['ref'] == ref and runs[-1]['red'] == red:
            runs[-1]['t'] += txt
        else:
            push('text', t=txt, bold=bold, italic=italic, ref=ref, red=red)
    # normalise whitespace inside text runs, drop empties; whitespace-only isn't a cross-ref
    clean = []
    for r in runs:
        if r['kind'] == 'text':
            r['t'] = re.sub(r'[ \t]+', ' ', r['t'])
            if r['t'] == '':
                continue
            if r['t'].strip() == '':
                r['bold'] = r['italic'] = r['ref'] = r['red'] = False
        clean.append(r)
    return clean


def merge_runs(runs):
    """Join adjacent text runs of identical style; collapse whitespace at joins."""
    out = []
    for r in runs:
        # spacing between runs is already baked in by the line-join logic; concat directly
        if r['kind'] == 'text' and out and out[-1]['kind'] == 'text' \
                and out[-1]['bold'] == r['bold'] and out[-1]['italic'] == r['italic'] \
                and out[-1]['ref'] == r['ref'] and out[-1].get('red') == r.get('red'):
            out[-1]['t'] = out[-1]['t'] + r['t']
        else:
            out.append(dict(r))
    for r in out:
        if r['kind'] == 'text':
            r['t'] = re.sub(r'\s+', ' ', r['t'])
    for r in out:
        if r['kind'] == 'text':
            r['t'] = re.sub(r' {2,}', ' ', r['t'])
    # drop leading/trailing pure-space runs, then trim the edge text runs
    while out and out[0]['kind'] == 'text' and out[0]['t'].strip() == '':
        out.pop(0)
    while out and out[-1]['kind'] == 'text' and out[-1]['t'].strip() == '':
        out.pop()
    if out and out[0]['kind'] == 'text':
        out[0]['t'] = out[0]['t'].lstrip()
    if out and out[-1]['kind'] == 'text':
        out[-1]['t'] = out[-1]['t'].rstrip()
    return out

def bullet_level(line):
    """If line starts with a Bodoni ornament bullet, return (level, marker_x); else None."""
    for s in line['spans']:
        if s['text'].strip() == '':
            continue
        if is_bullet_font(s['font']):
            mx = s['bbox'][0]
            margin = line.get('xedge', 36)
            lvl = 2 if mx > margin + 12 else 1
            return lvl
        return None   # first non-blank span isn't a bullet
    return None

def finalize_body(raw):
    """raw = list of body lines [{block,bullet(level or None),runs,page}] ->
    paragraphs & bullets. Consecutive non-bullet lines in the same PDF block join
    into one paragraph; each bullet marker starts a new bullet (continuation lines
    in the same block that are NOT new bullets fold into the current bullet)."""
    blocks = []
    cur = None          # currently open paragraph/bullet being appended to
    for ln in raw:
        if ln['bullet']:
            cur = {'type': 'bullet', 'level': ln['bullet'], 'runs': list(ln['runs']),
                   'block': ln['block']}
            blocks.append(cur)
        else:
            same = cur is not None and cur['block'] == ln['block']
            if same:
                prev = cur['runs']; nxt = ln['runs']
                tight = False
                if prev and prev[-1]['kind'] == 'text':
                    t = prev[-1]['t'].rstrip()
                    if re.search(r'[A-Za-zÁÉÍÓÚáéíóúñüÑÜ]-$', t):
                        prev[-1]['t'] = t[:-1]           # de-hyphenate line break
                        tight = True
                if not tight:                            # keep a separating space on a styled run
                    if prev and prev[-1]['kind'] == 'text':
                        if not prev[-1]['t'].endswith(' '):
                            prev[-1]['t'] += ' '
                    elif nxt and nxt[0]['kind'] == 'text':
                        if not nxt[0]['t'].startswith(' '):
                            nxt[0]['t'] = ' ' + nxt[0]['t']
                    else:
                        prev.append({'kind': 'text', 't': ' ', 'bold': False,
                                     'italic': False, 'ref': False, 'red': False})
                cur['runs'].extend(nxt)
            else:
                cur = {'type': 'p', 'level': 0, 'runs': list(ln['runs']),
                       'block': ln['block']}
                blocks.append(cur)
    # merge runs & drop empties
    out = []
    for b in blocks:
        b['runs'] = merge_runs(b['runs'])
        if not b['runs']:
            continue
        b.pop('block', None)
        if b['type'] == 'p':
            b.pop('level', None)
        out.append(b)
    return out


def check_montage_coords(pack, doc):
    """Montage clip regions are measured in the points of ONE PDF edition. If the
    pack now points at a differently-laid-out file, the regions would mask the
    wrong text and the run would still 'succeed' — so refuse to guess."""
    if not pack.montages:
        return
    bad = [m for m in pack.montages if m['page'] > doc.page_count]
    if bad:
        raise langpack.PackError(
            f'langs/{pack.code}/lang.json: montage {bad[0]["name"]!r} is on page '
            f'{bad[0]["page"]}, but {pack.current["pdf"]} only has {doc.page_count} pages.\n'
            f'  Montage "page"/"clip" coordinates belong to one specific PDF. If you '
            f'changed the source file, re-measure them with:\n'
            f'    python tools/inspect_pdf.py {pack.code} --grid <page>')


def warn_if_no_red(pack, nodes):
    """The what's-new diff is derived from text the publisher printed in dark red.
    No red means no diff — say so, or a contributor sees an empty "What's New" and
    has no way to tell whether the pipeline or the PDF is at fault."""
    if len(pack.versions) < 2:
        return 0
    red = sum(1 for n in nodes for b in n['blocks'] for r in b['runs'] if r.get('red'))
    if red == 0:
        print(f'  [warn] v{pack.current["v"]} is not the first version, but no dark-red text '
              f'was found in {pack.current["pdf"]}.\n'
              f'         "What\'s New" is built from the red markup the publisher uses for '
              f'additions; without it the section will be empty.')
    return red


def parse(pack):
    """The edition the site is built from: the newest, with its montages masked."""
    pdf = pack.require_pdf()
    doc_check = fitz.open(pdf)
    check_montage_coords(pack, doc_check)
    return parse_pdf(pdf, masks_for(pack))


def parse_pdf(pdf, masks):
    """Any edition. Older ones are read for comparison only, with no masking:
    their montage clips belong to a different layout."""
    lines, doc = collect_lines(pdf, masks)
    nodes = []
    cur = None

    def new_node(level, title, page, title_runs=None):
        nonlocal cur
        node = {'level': level, 'title': title, 'page': page, 'raw': []}
        if title_runs:
            node['title_runs'] = title_runs
        nodes.append(node)
        cur = node
        return node

    i = 0
    N = len(lines)
    while i < N:
        line = lines[i]
        lvl = line_is_heading(line)
        if lvl is not None:
            parts = [line_text(line)]
            hspans = list(line['spans'])
            j = i + 1
            best = lvl
            while j < N:
                nl = lines[j]
                nlvl = line_is_heading(nl)
                if nlvl is None:
                    break
                gap = nl['y'] - lines[j-1]['y1']
                if nlvl == best and nl['page'] == line['page'] and nl['col'] == line['col'] and -2 <= gap < 13:
                    parts.append(line_text(nl))
                    hspans.append({'font': 'ArnoPro-Regular', 'text': ' ', 'size': 9, 'color': 0})
                    hspans.extend(nl['spans'])
                    j += 1
                else:
                    break
            plain = re.sub(r'\(\s*\)', '', norm(' '.join(parts)))
            plain = re.sub(r'\s+', ' ', plain).strip(' .')
            truns = merge_runs(build_runs(hspans))
            has_icon = any(r['kind'] == 'icon' for r in truns)
            # NB: a red heading means "something in this entry changed", NOT "this
            # entry is new" — see tools/history.py. Whether it is new is decided by
            # comparing editions, not by reading a colour.
            new_node(best, plain, line['page'], truns if has_icon else None)
            i = j
            continue
        if cur is None:
            new_node(1, '(frontmatter)', line['page'])
        # drop illustration-credit fragments bleeding in from example-card artwork
        if CREDIT.search(line_text(line)):
            i += 1
            continue
        runs = build_runs(line['spans'])
        if runs:
            cur['raw'].append({'block': line['block'], 'bullet': bullet_level(line),
                               'runs': runs, 'page': line['page']})
        i += 1

    for n in nodes:
        n['blocks'] = finalize_body(n.pop('raw'))
    return nodes, doc

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/parse_grimoire.py <lang>', file=sys.stderr)
        return 2
    pack = langpack.load(sys.argv[1])
    nodes, doc = parse(pack)
    json.dump(nodes, open(pack.nodes_path, 'w', encoding='utf-8'), ensure_ascii=False)
    # diagnostics
    from collections import Counter
    lv = Counter(n['level'] for n in nodes)
    print('nodes:', len(nodes), 'by level:', dict(lv))
    warn_if_no_red(pack, nodes)
    print('--- H1 / H2 titles ---')
    for n in nodes:
        if n['level'] <= 2:
            print(f"  L{n['level']} p{n['page']:>2} {n['title'][:60]!r}")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
