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
Run this for each PDF; it writes <out>.json.
"""
import fitz, json, re, sys, unicodedata

# --- Arkham icon font: PUA codepoint -> semantic name (derived from p49) ---
ICON_MAP = {
    0xF250:'willpower', 0xF251:'agility', 0xF252:'intellect', 0xF253:'combat', 0xF26C:'wild',
    0xF254:'rogue', 0xF255:'survivor', 0xF256:'guardian', 0xF257:'mystic', 0xF258:'seeker',
    0xF259:'action', 0xF25A:'free', 0xF26D:'reaction',
    0xF25B:'skull', 0xF25C:'cultist', 0xF25D:'autofail', 0xF25E:'elderthing',
    0xF25F:'eldersign', 0xF260:'tablet', 0xF261:'unique', 0xF263:'perinvestigator',
    0xF278:'codex',
}
TEAL = 0x306360           # cross-reference colour
# illustration credits from embedded example cards (not rules prose)
CREDIT = re.compile(r'(Illus\.|©\s*20\d\d\b.*FFG|Pixoloid\s+Studios)', re.I)
PAGE_MID = 306            # column split for a 612pt-wide page
FOOT_Y = 748              # ignore footer page numbers below this

def is_head_font(font):   # any Teutonic variant is a heading face
    return 'Teutonic' in font
def is_bullet_font(font):
    return 'Bodoni' in font or 'Ornament' in font
def is_icon_font(font):
    return 'ArkhamHorror' in font

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

def collect_lines(pdf):
    """Return list of logical lines in reading order across the doc.
    Each line: {page, col, y, x0, spans:[...]} where a span keeps font/size/color/text."""
    doc = fitz.open(pdf)
    out = []
    gblock = 0
    for pno in range(doc.page_count):
        page = doc[pno]
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
                y0 = min(s['bbox'][1] for s in spans)
                y1 = max(s['bbox'][3] for s in spans)
                if y0 >= FOOT_Y:            # footer page number
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
        # merge with previous compatible text run
        if runs and runs[-1]['kind'] == 'text' and runs[-1]['bold'] == bold \
                and runs[-1]['italic'] == italic and runs[-1]['ref'] == ref:
            runs[-1]['t'] += txt
        else:
            push('text', t=txt, bold=bold, italic=italic, ref=ref)
    # normalise whitespace inside text runs, drop empties; whitespace-only isn't a cross-ref
    clean = []
    for r in runs:
        if r['kind'] == 'text':
            r['t'] = re.sub(r'[ \t]+', ' ', r['t'])
            if r['t'] == '':
                continue
            if r['t'].strip() == '':
                r['bold'] = r['italic'] = r['ref'] = False
        clean.append(r)
    return clean


def merge_runs(runs):
    """Join adjacent text runs of identical style; collapse whitespace at joins."""
    out = []
    for r in runs:
        # spacing between runs is already baked in by the line-join logic; concat directly
        if r['kind'] == 'text' and out and out[-1]['kind'] == 'text' \
                and out[-1]['bold'] == r['bold'] and out[-1]['italic'] == r['italic'] \
                and out[-1]['ref'] == r['ref']:
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
                                     'italic': False, 'ref': False})
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


def parse(pdf):
    lines, doc = collect_lines(pdf)
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

if __name__ == '__main__':
    pdf = sys.argv[1]
    out = sys.argv[2]
    nodes, doc = parse(pdf)
    json.dump(nodes, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    # diagnostics
    from collections import Counter
    lv = Counter(n['level'] for n in nodes)
    print('nodes:', len(nodes), 'by level:', dict(lv))
    print('--- H1 / H2 titles ---')
    for n in nodes:
        if n['level'] <= 2:
            print(f"  L{n['level']} p{n['page']:>2} {n['title'][:60]!r}")
    print('--- first 12 H3 ---')
    c = 0
    for n in nodes:
        if n['level'] == 3:
            print(f"  p{n['page']:>2} {n['title'][:50]!r}  blocks={len(n['blocks'])}")
            c += 1
            if c >= 12:
                break
