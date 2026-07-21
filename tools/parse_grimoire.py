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
from icons import ICON_MAP, icon_name, is_alien_font, is_icon_font

TEAL = 0x306360           # cross-reference colour
# illustration credits from embedded example cards (not rules prose)
CREDIT = re.compile(r'(Illus\.|©\s*20\d\d\b.*FFG|Pixoloid\s+Studios)', re.I)
PAGE_MID = 306            # column split for a 612pt-wide page
FOOT_Y = 748              # ignore footer page numbers below this

def is_head_font(font):   # any Teutonic variant is a heading face
    return 'Teutonic' in font
def is_bullet_font(font):
    return 'Bodoni' in font or 'Ornament' in font

def _rgb(s):
    c = s.get('color', 0)
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def is_red(s):
    """Any of the book's dark reds. Which red it is, is a separate question —
    see `is_callout_red`."""
    r, g, b = _rgb(s)
    return r >= 0x80 and g <= 0x40 and b <= 0x40 and (r - g) >= 0x40


# The book prints THREE dark reds and means three different things by them:
#
#   #921D1E          a player window — the free-trigger icon and the label beside
#                    it, in the phase diagrams. 8 of each in EVERY edition.
#   #8B1F24 #8B1F23  a STOP! callout. In every edition too.
#   #911D1D          text added in THIS edition. 232 spans in EN v1.1, and not
#                    one in EN v1.0 or ES v1.0 — which, being first editions,
#                    added nothing. That is the proof of which red is which.
#
# Only the last is a diff. The other two are the book saying "this is a window" /
# "read this twice", and reading them as additions made the English STOP! box
# claim it was "Rewritten in 1.1" and every "Player Window" label light up as new.
#
# The window red and the addition red differ by ONE on two channels
# (#921D1E vs #911D1D), so they are matched EXACTLY. There is no tolerance to
# tune: within one document a colour is one integer, and any tolerance at all
# would merge these two.
#
# Neither colour is hardcoded. Each edition is asked, using the one anchor that
# cannot lie about each:
#   the callout red — the STOP! heading is, by definition, printed in it;
#   the window red  — the free-trigger icon opens every window box, and it is an
#                     icon-font glyph, so it cannot be confused with prose. (The
#                     icons inside ADDED text are other glyphs — reaction, action,
#                     combat, agility — never `free`.)
#
# parse_pdf sets these for the document it is reading, and they are the default
# for everything inside that call. Anything reading spans from a document parse_pdf
# did not open — card_anatomy.py does — must pass its own document's reds, or it
# would silently judge one edition's colours by another's.
WINDOW_ICON = 'free'
_REDS = (None, None)           # (callout, window) for the document being parsed
_KEEP = object()               # "use the document parse_pdf is currently reading"


def _commonest(counter):
    return max(counter, key=counter.get) if counter else None


def _learn_reds(spans_iter):
    """-> (callout_red, window_red) for one edition, read off its own printing."""
    callout, window = {}, {}
    for s in spans_iter:
        if not s['text'].strip() or not is_red(s):
            continue
        if is_icon_font(s['font']):
            if any(icon_name(ord(ch)) == WINDOW_ICON for ch in s['text'] if ch.strip()):
                window[s['color']] = window.get(s['color'], 0) + 1
        elif is_head_font(s['font']) and s['size'] >= 15.5:
            callout[s['color']] = callout.get(s['color'], 0) + 1
    return _commonest(callout), _commonest(window)


def learn_reds(lines):
    return _learn_reds(s for ln in lines for s in ln['spans'])


def reds_of_doc(doc):
    """The same question, asked of a whole document. For readers that open a PDF
    themselves instead of going through parse_pdf."""
    return _learn_reds(
        s for page in doc
        for b in page.get_text('dict')['blocks'] if b['type'] == 0
        for l in b['lines'] for s in l['spans'])


def is_structural_red(s, reds=_KEEP):
    """Red because of what this text IS (a callout, a player window) rather than
    because this edition added it. Matched exactly — see the note above."""
    callout, window = _REDS if reds is _KEEP else reds
    c = s.get('color', 0)
    return (callout is not None and c == callout) or (window is not None and c == window)


def is_callout_red(s, reds=_KEEP):
    callout = (_REDS if reds is _KEEP else reds)[0]
    return callout is not None and s.get('color', 0) == callout


def is_teal(s):
    """The book's teal, used for cross-references and for subsection headings.
    Matched by range, not by one value: the Spanish and English editions print it
    a shade apart (#306360 vs #30635F)."""
    r, g, b = _rgb(s)
    return r < 0x50 and g > 0x50 and abs(g - b) <= 0x20 and g > r + 0x20


def is_new_red(s, reds=_KEEP):
    """True for the dark-red text that marks content added in this version — and
    only that. See the note above: two of the book's three reds are structural."""
    if is_icon_font(s['font']):
        return False
    if not is_red(s):
        return False
    if is_structural_red(s, reds):         # a callout or a player window, not a diff
        return False
    if is_head_font(s['font']) and s['size'] >= 15.5:
        return False
    return True


def heading_role(spans):
    """What the book is doing with this heading, read from how it prints it.

    A big red heading is a STOP! callout; a big teal one opens a subsection.
    Anything else is an ordinary heading — including the Spanish "La regla
    nefasta", which is merely set two points larger than its siblings.
    """
    head = [s for s in spans if is_head_font(s['font']) and s['text'].strip()]
    if not head:
        return None
    big = [s for s in head if s['size'] >= 15.5]
    if not big:
        return None
    # the callout's own red, not merely a red: a chapter heading that an edition
    # printed red because it added it is an addition, not a notice
    if any(is_callout_red(s) for s in big):
        return 'callout'
    if all(is_teal(s) for s in big):
        return 'subhead'
    return None

def span_kind(s):
    f, sz = s['font'], s['size']
    # 22+ = cover title (38), card-diagram callout numbers (31.2), em-dash (24.4): not headings
    if is_head_font(f) and 13.0 <= sz < 22.0:
        if sz >= 17.5: return ('H', 1)
        if sz >= 15.5: return ('H', 2)
        return ('H', 3)
    return ('B', 0)

# A discretionary hyphen: invisible unless the line actually breaks there. The German
# edition sets 718 of them ("Kampagnen<shy>spiel"), the other editions none. Anywhere
# but at the end of a line it is punctuation the reader never sees, so it is dropped;
# the one at a line end IS printed, and finalize_body joins the word back over it.
SOFT_HYPHEN = '­'


def norm(t):
    return re.sub(r'\s+', ' ', t.replace(SOFT_HYPHEN, '')).strip()

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


def column_edges_dense(blocks):
    """Like column_edges, but a candidate column is kept only if a fair share of the page's TEXT
    starts in it. A card reference that WRAPPED across a line ("Name (\\n 164) …") leaves a lone
    fragment far to the right; the plain detector reads that as a second column and flings the
    wrapped number to the end of the page. Requiring support treats a single-column page — even one
    dotted with wrapped card refs — as the single column it is, while still finding real columns.

    Support is counted in LINES, not blocks. Counting blocks looked equivalent and was not: the
    publisher sometimes sets a whole column as ONE PDF block, and the taboo list's second column
    is exactly that — one block, forty lines. Needing three blocks threw that column away, the
    page collapsed to a single column, and its two columns came out interleaved line by line.
    A wrapped card reference is one line; a real column is dozens, so lines tell them apart and
    a column's own typesetting cannot fool the count.

    Used only by the FAQ parse (faq_seticons.parse_with_icons), whose Q&A/rulings pages are
    single-column but riddled with wrapped card references; the Grimoire keeps the plain detector."""
    weighted = []                                # (block x0, how many lines that block holds)
    for b in blocks:
        text_lines = [l for l in b['lines'] if any(s['text'].strip() for s in l['spans'])]
        if not text_lines:
            continue
        x0 = min(s['bbox'][0] for l in text_lines for s in l['spans'] if s['text'].strip())
        weighted.append((x0, len(text_lines)))
    if not weighted:
        return [0.0]
    weighted.sort()
    total = sum(n for _x, n in weighted)
    clusters = [[weighted[0]]]
    for x, n in weighted[1:]:
        if x - clusters[-1][-1][0] <= 40:
            clusters[-1].append((x, n))
        else:
            clusters.append([(x, n)])
    need = max(3, int(0.12 * total))
    edges = []
    for c in clusters:
        if not edges or sum(n for _x, n in c) >= need:   # always keep the leftmost (main) column
            edges.append(min(x for x, _n in c))
    return edges or [weighted[0][0]]


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

def build_runs(spans, reds=_KEEP):
    """Turn a list of spans into inline runs, merging adjacent text of same style.

    `reds` is (callout_red, window_red) for the edition these spans came from
    (see `is_new_red`). Leave it alone inside parse_pdf; pass it when the spans
    come from a document opened elsewhere."""
    runs = []
    def push(kind, **kw):
        runs.append(dict(kind=kind, **kw))
    for s in spans:
        f = s['font']; txt = s['text']
        if is_icon_font(f):
            for ch in txt:
                cp = ord(ch)
                name = icon_name(cp)
                if name:
                    push('icon', name=name)
                elif ch.strip():
                    push('icon', name='unknown', cp='U+%04X' % cp)
            continue
        if is_bullet_font(f):
            continue  # bullet marker handled by caller
        bold = 'Bold' in f or 'Smbd' in f or 'Semibold' in f
        italic = 'Italic' in f or '-It' in f
        ref = (s.get('color', 0) == TEAL)
        red = is_new_red(s, reds)
        # The alien script is ordinary text in an extraordinary face (see icons.is_alien_font):
        # marked, never merged with the roman around it, so the site can draw it as the book
        # does instead of printing the letters the reader is not meant to see.
        alien = is_alien_font(f)
        # merge with previous compatible text run
        if runs and runs[-1]['kind'] == 'text' and runs[-1]['bold'] == bold \
                and runs[-1]['italic'] == italic and runs[-1]['ref'] == ref \
                and runs[-1]['red'] == red and bool(runs[-1].get('alien')) == alien:
            runs[-1]['t'] += txt
        else:
            push('text', t=txt, bold=bold, italic=italic, ref=ref, red=red)
            if alien:
                runs[-1]['alien'] = True
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
    return _drop_soft_hyphens(clean)


def _drop_soft_hyphens(runs):
    last = max((i for i, r in enumerate(runs) if r['kind'] == 'text'), default=None)
    for i, r in enumerate(runs):
        if r['kind'] != 'text':
            continue
        breaks = (i == last and r['t'].rstrip().endswith(SOFT_HYPHEN))
        r['t'] = r['t'].replace(SOFT_HYPHEN, '')
        if breaks:
            r['t'] += SOFT_HYPHEN
    return runs


def merge_runs(runs):
    """Join adjacent text runs of identical style; collapse whitespace at joins."""
    out = []
    for r in runs:
        # spacing between runs is already baked in by the line-join logic; concat directly
        # `alien` counts as a style here: it is a different FACE, and merging an alien run into
        # the roman beside it silently dropped the flag (the merge keeps the earlier dict), so
        # the script reached the page as ordinary letters however carefully it was marked.
        if r['kind'] == 'text' and out and out[-1]['kind'] == 'text' \
                and out[-1]['bold'] == r['bold'] and out[-1]['italic'] == r['italic'] \
                and out[-1]['ref'] == r['ref'] and out[-1].get('red') == r.get('red') \
                and bool(out[-1].get('alien')) == bool(r.get('alien')):
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

# The book marks its two kinds of bullet with two ornament glyphs, and it uses the
# same two in every edition: 'Æ' 458x / '=' 86x in ES v1.0, 465x / 84x in EN v1.1.
# They are characters of the ornament font, so they mean the same thing whatever
# the language — like the game icons in icons.py, and unlike where they sit.
#
# Where they sit was the old rule, and it was wrong: it called a bullet nested if
# it began more than 12pt right of its column. The editions do not lay out alike —
# the same nested bullet starts at x=326 in Spanish (a 2-column page) and x=938 in
# English (a 2-page spread) — so the same sentence came out nested in one language
# and top-level in the other, and got a different bullet in each.
BULLET_MARKS = {'Æ': 1, '=': 2}


def bullet_level(line):
    """If the line opens with an ornament bullet, the level the book gives it."""
    for s in line['spans']:
        if s['text'].strip() == '':
            continue
        if is_bullet_font(s['font']):
            return BULLET_MARKS.get(s['text'].strip()[:1], 1)
        return None   # first non-blank span isn't a bullet
    return None

# A bullet whose continuation the PDF puts in a *different* text block. The join below is
# normally keyed on the PDF's own block id, which is the honest signal — except when the
# publisher sets part of a bullet in italic and the PDF splits it off as its own block. The
# page shows one bullet ("…investigator expansions. (For example, if playing with…"); the
# parse shows the bullet, then an orphan paragraph starting mid-sentence.
#
# Off by default, because the Grimoire's parse is tuned and measured against its printed page
# and this changes how blocks join. The FAQ turns it on (faq_seticons.parse_with_icons), which
# is where the split actually shows up.
FOLD_BULLET_CONTINUATION = False
_HANG = 6.0            # how far a continuation line is indented past its bullet's marker
_STEP = 22.0           # the biggest vertical gap that is still the next line, not a new block


def _continues_bullet(cur, ln):
    """True when this line is the open bullet's next line, set in a block of its own.

    Read off the page's geometry, not its words: same page and column, indented to the
    bullet's hanging indent rather than back at the margin, and one line-step below it."""
    if not FOLD_BULLET_CONTINUATION or cur is None or cur.get('type') != 'bullet':
        return False
    if ln.get('page') != cur.get('page') or ln.get('col') != cur.get('col'):
        return False
    if ln.get('x0') is None or cur.get('x0') is None:
        return False
    if ln['x0'] < cur['x0'] + _HANG:
        return False                      # back at the margin: a new paragraph, not a wrap
    gap = ln.get('y', 0) - cur.get('lasty', 0)
    return 0 < gap <= _STEP


def finalize_body(raw):
    """raw = list of body lines [{block,bullet(level or None),runs,page,col,x0,y}] ->
    paragraphs & bullets. Consecutive non-bullet lines in the same PDF block join
    into one paragraph; each bullet marker starts a new bullet (continuation lines
    in the same block that are NOT new bullets fold into the current bullet)."""
    blocks = []
    cur = None          # currently open paragraph/bullet being appended to
    for ln in raw:
        if ln['bullet']:
            cur = {'type': 'bullet', 'level': ln['bullet'], 'runs': list(ln['runs']),
                   'block': ln['block'], 'page': ln.get('page'), 'col': ln.get('col'),
                   'x0': ln.get('x0'), 'lasty': ln.get('y')}
            blocks.append(cur)
        else:
            same = (cur is not None
                    and (cur['block'] == ln['block'] or _continues_bullet(cur, ln)))
            if same:
                prev = cur['runs']; nxt = ln['runs']
                tight = False
                if prev and prev[-1]['kind'] == 'text':
                    t = prev[-1]['t'].rstrip()
                    # any letter, in any language, before a printed hyphen or a soft
                    # one the typesetter actually broke on
                    if re.search(r'[^\W\d_][-' + SOFT_HYPHEN + r']$', t):
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
                cur['lasty'] = ln.get('y', cur.get('lasty'))
            else:
                cur = {'type': 'p', 'level': 0, 'runs': list(ln['runs']),
                       'block': ln['block'], 'page': ln.get('page'), 'col': ln.get('col'),
                       'x0': ln.get('x0'), 'lasty': ln.get('y')}
                blocks.append(cur)
    # merge runs & drop empties
    out = []
    for b in blocks:
        b['runs'] = merge_runs(b['runs'])
        if not b['runs']:
            continue
        for k in ('block', 'page', 'col', 'x0', 'lasty'):
            b.pop(k, None)                 # bookkeeping for the joins above; not part of a block
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
    global _REDS
    lines, doc = collect_lines(pdf, masks)
    # Ask this edition which of its reds mean what, before any run is built from
    # them. Set per document: history.py parses the older editions through here
    # too, and each prints its own shades.
    _REDS = learn_reds(lines)
    nodes = []
    cur = None

    def new_node(level, title, page, title_runs=None, role=None):
        nonlocal cur
        node = {'level': level, 'title': title, 'page': page, 'raw': []}
        if title_runs:
            node['title_runs'] = title_runs
        if role:
            node['role'] = role
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
            # NB: a red heading at entry size means "something in this entry
            # changed", NOT "this entry is new" — see tools/history.py. Whether it
            # is new is decided by comparing editions, not by reading a colour.
            # A red heading at *subsection* size is a different thing entirely: a
            # STOP! callout. heading_role tells them apart.
            new_node(best, plain, line['page'], truns if has_icon else None,
                     heading_role(hspans))
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
                               'runs': runs, 'page': line['page'],
                               'col': line['col'], 'x0': line['x0'], 'y': line['y']})
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
