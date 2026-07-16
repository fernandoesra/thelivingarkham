# -*- coding: utf-8 -*-
"""Assemble parsed nodes -> final structured data model for The Living Arkham.
  * groups nodes into top-level sections (ordered, roman-numeral aware)
  * assigns stable slugs/anchors to sections & entries
  * resolves cross-references ("Consulta también ... página N") into inline links
  * attaches rendered figures to image sections
  * validates entry counts & cross-reference integrity

Everything language-specific — the section list, the cross-reference wording, the
auto-link vocabulary, the version history — comes from that language's pack
(langs/<lang>/lang.json). This file knows no language.

Usage:  python tools/assemble.py <lang>
Outputs data/grimoire_<lang>.json plus a validation report.
"""
import json, re, sys, os, unicodedata
import langpack
from langpack import slugify

def norm(t):
    t = (t or '').strip().lower().replace('“','"').replace('”','"').replace('’',"'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip(' .:"')

# length-preserving accent fold (positions stay valid in the original string, so
# regex matches on the folded text map straight back onto the source text).
# The 1:1 invariant is enforced in langpack.validate_fold, not just documented.
fold = langpack.fold

def title_variants(title):
    """Splittable forms of an entry title for auto-linking: drop parentheticals and
    quotes, split on ',' and '/'. E.g. 'Agotar, Agotado' -> ['Agotar','Agotado']."""
    t = re.sub(r'\([^)]*\)', ' ', title).replace('“','').replace('”','').replace('"','')
    return [p.strip(' .:') for p in re.split(r'[,/]', t) if p.strip(' .:')]

ROMAN = re.compile(r'^\s*([IVXLC]+)\.\s*(.*)$')

def flat_text(runs):
    return ''.join(r.get('t','') for r in runs if r['kind'] == 'text')

def assemble(pack, nodes, images):
    lang = pack.code
    seclist = pack.sections
    by_num = {}
    for idx, s in enumerate(seclist):
        if s['num']: by_num[s['num']] = idx
    started = [False]*len(seclist)
    sections = [None]*len(seclist)
    def mk(idx):
        sc = seclist[idx]
        s = {'num':sc['num'],'key':sc['key'],'id':sc['id'],'title':sc['title'],'kind':sc['kind'],
             'intro':[], 'entries':[], 'figures':[]}
        for f in sc.get('figures', []):
            info = images.get(f)
            if info: s['figures'].append({'file':info['file'],'w':info['w'],'h':info['h'],'page':info['page']})
        sections[idx]=s
        return s

    intro_blocks = []
    cur = None            # current section dict
    cur_kind = None

    def match_section(title):
        m = ROMAN.match(title)
        n = norm(title)
        # index -> stop
        if n.startswith(pack.parse['indexStart']):
            return 'INDEX'
        # roman numeral exact match to an unstarted section
        if m:
            num = m.group(1)
            if num in by_num and not started[by_num[num]]:
                return by_num[num]
        # numberless specials matched by name (e.g. the quick-reference sheet)
        for idx, sc in enumerate(seclist):
            if started[idx] or sc['num']:      # only numberless / by-name specials here
                continue
            if n.startswith(norm(sc['title'])):
                return idx
        # numbered specials matched by name (a book may misprint a numeral: the ES
        # edition labels its "Reimpresiones modificadas" chapter XII twice)
        for idx, sc in enumerate(seclist):
            if started[idx]:
                continue
            if n.startswith(norm(sc['title'])) or norm(sc['title']) in n:
                return idx
        return None

    reached_first = False
    for node in nodes:
        lvl = node['level']; title = node['title']; blocks = node['blocks']
        if lvl == 1:
            hit = match_section(title)
            if hit == 'INDEX':
                break
            if isinstance(hit, int):
                if not started[hit]:
                    started[hit] = True
                    cur = mk(hit); cur_kind = cur['kind']
                    # section-start node body -> section intro
                    if blocks:
                        cur['intro'].extend(blocks)
                    reached_first = True
                    continue
        if not reached_first:
            # front matter: capture the "how to use" explanation
            if norm(title).startswith(pack.parse['introStart']) and blocks:
                intro_blocks.extend(blocks)
            elif intro_blocks and blocks and lvl != 1:
                intro_blocks.extend(blocks)
            continue
        # content of current section
        if cur is None:
            continue
        if cur_kind == 'figures':
            # ignore dense figure text; keep only the section intro already captured
            continue
        if lvl == 1:
            # wrapped banner fragment or stray -> fold body into intro if any
            if blocks:
                cur['intro'].extend(blocks)
            continue
        # lvl 2 or 3 -> an entry (sub-heading). Skip empty titleless.
        if not title:
            continue
        entry = {'title':title, 'blocks':blocks, 'page':node['page'], 'sub': lvl==2}
        if node.get('title_runs'):
            entry['titleRuns'] = node['title_runs']
        if node.get('red_title'):
            entry['_new'] = True
        cur['entries'].append(entry)
    # A section the parser never found is silently absent from the site, which is
    # the worst way to fail: the run "succeeds" and the chapter is just gone.
    missing = [seclist[i] for i in range(len(seclist)) if not started[i]]
    if missing:
        want = ', '.join(f'{s["num"] + ". " if s["num"] else ""}{s["title"]}' for s in missing)
        raise langpack.PackError(
            f'langs/{lang}/lang.json: {len(missing)} of {len(seclist)} sections were never '
            f'found in {pack.current["pdf"]}:\n    {want}\n'
            f'  A section is matched by its roman numeral ("I.", "II.", …) or by its "title" '
            f'matching the heading printed in the PDF.\n'
            f'  See the headings your PDF actually has:\n'
            f'    python tools/inspect_pdf.py {lang} --sections')
    sections = [s for s in sections if s]
    # assign entry ids (unique within language)
    used = set()
    title_index = {}       # norm(title) -> entry id
    for s in sections:
        base = s['id']
        for e in s['entries']:
            eid = slugify(e['title'])
            full = f'{base}--{eid}'
            k = full; i = 2
            while k in used:
                k = f'{full}-{i}'; i += 1
            used.add(k)
            e['id'] = k
            title_index.setdefault(norm(e['title']), k)
    # attach montage figures (example card-art resources) to their glossary entries
    entry_by_title = {}
    for s in sections:
        for e in s['entries']:
            entry_by_title.setdefault(norm(e['title']), e)
    for m in pack.montages:
        e = entry_by_title.get(norm(m['entry']))
        info = images.get(m['name'])
        if e is None or not info:
            print(f'  [warn] montage {m["name"]!r} not attached (entry={m["entry"]!r} found={e is not None} img={info is not None})')
            continue
        e.setdefault('figures', []).append({
            'file': info['file'], 'w': info['w'], 'h': info['h'],
            'srcpage': m.get('srcpage', info.get('page')), 'alt': m['alt'], 'info': m['info']})
    # re-insert standalone symbols (drawn as vectors, invisible to the text parser)
    for ins in pack.inline_symbols:
        e = entry_by_title.get(norm(ins['entry']))
        if e is None:
            print(f'  [warn] inline symbol: entry {ins["entry"]!r} not found'); continue
        anchor = norm(ins['after']); idx = None
        for i, b in enumerate(e['blocks']):
            if norm(flat_text(b['runs'])).endswith(anchor):
                idx = i; break
        if idx is None:
            print(f'  [warn] inline symbol: anchor {ins["after"]!r} not found in {ins["entry"]!r}'); continue
        e['blocks'].insert(idx+1, {'type':'sym', 'runs':[{'kind':'icon','name':ins['icon']}]})
    intro_section = {'num':'','key':'intro','id':'intro','title':pack.parse['introTitle'],
                     'kind':'intro','intro':intro_blocks,'entries':[],'figures':[]}
    return intro_section, sections, title_index

def linkify(sections, title_index, pack):
    trig = re.compile(pack.patterns['trigger'], re.I)
    pageword = pack.patterns['pageWord']
    pageref = re.compile(pack.patterns['pageRef'], re.I)
    quote = re.compile(r'([“"])(.+?)([”"])')
    linkcount = [0]
    def process_run(run, ctx_has_trig):
        """Split a text run into inline runs at cross-ref titles (links) and
        page references ('en la página 13' -> a pageref chip)."""
        if run['kind'] != 'text':
            return [run]
        t = run['t']
        v = run.get('v')
        repls = []                                        # (start, end, newrun)
        for m in quote.finditer(t):
            key = norm(m.group(2)); tgt = title_index.get(key)
            if not tgt:
                continue
            after = t[m.end():m.end()+28]; before = t[max(0, m.start()-45):m.start()]
            if not (ctx_has_trig or re.search(pageword, after, re.I) or trig.search(before)):
                continue
            lk = {'kind':'link','t':m.group(0),'target':tgt,
                  'bold':run.get('bold',False),'italic':run.get('italic',False)}
            if v: lk['v'] = v
            repls.append((m.start(), m.end(), lk)); linkcount[0]+=1
        if ctx_has_trig:
            for m in pageref.finditer(t):
                repls.append((m.start(), m.end(), {'kind':'pageref','n':re.sub(r'\s+','',m.group(1))}))
        if not repls:
            return [run]
        repls.sort(key=lambda x: x[0])
        out = []; last = 0
        for st, en, nr in repls:
            if st < last:
                continue                                  # skip overlaps
            if st > last:
                out.append({**run, 't': t[last:st]})
            out.append(nr); last = en
        if last < len(t):
            out.append({**run, 't': t[last:]})
        return out
    def process_blocks(blocks):
        for b in blocks:
            ctx = trig.search(flat_text(b['runs'])) is not None
            newruns = []
            for r in b['runs']:
                newruns.extend(process_run(r, ctx))
            b['runs'] = newruns
    for s in sections:
        process_blocks(s['intro'])
        for e in s['entries']:
            process_blocks(e['blocks'])
    return linkcount[0]


def autolink(sections, title_index, pack):
    """Turn the first mention of a related glossary term into an inline link, so the
    reader can jump straight to it (e.g. 'Robar 1 carta' -> the 'Robar cartas' entry).
    Conservative on purpose: glossary only, distinctive terms + curated aliases,
    first occurrence per target per entry, never self-links, capped per entry."""
    al = pack.autolink
    # the lists are matched against accent-folded text, so fold them on load:
    # a pack may spell them either way ('aparición' or 'aparicion') and mean the same.
    stop = {fold(x) for x in al.get('stop', [])}
    allow1 = {fold(x) for x in al.get('allowSingleWord', [])}
    cap = al.get('cap', 12)
    phrases = {}                                   # folded phrase -> target id
    def add(phrase, tgt, force=False):
        f = fold(re.sub(r'\s+', ' ', phrase).strip(' .:'))
        if not f or (f in stop and not force):
            return
        if not force and (len(f) < 3 or (len(f.split()) == 1 and f not in allow1)):
            return
        phrases.setdefault(f, tgt)
    for s in sections:
        if s.get('kind') != 'glossary':
            continue
        for e in s['entries']:
            for pv in title_variants(e['title']):
                add(pv, e['id'])
    for alias, tgt_title in al.get('alias', {}).items():
        tid = title_index.get(norm(tgt_title))
        if tid:
            add(alias, tid, force=True)
        else:
            print(f'  [warn] autolink alias target not found: {tgt_title!r} '
                  f'(check "autolink.alias" in langs/{pack.code}/lang.json — the value must be '
                  f'a glossary entry title exactly as printed)')
    if not phrases:
        return 0
    tgt_of = dict(phrases)
    # longest phrases first so 'cartas de apoyo' wins over any shorter overlap
    alt = '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    rx = re.compile(r'(?<![0-9a-z])(' + alt + r')(?![0-9a-z])')
    count = [0]
    def process_group(group, e, used, n_here):
        """Match across a run of consecutive text runs (a phrase like 'Robar 1 carta'
        may be split by bold formatting), then rebuild preserving original formatting
        outside the matched spans."""
        text = ''.join(r['t'] for r in group); ft = fold(text)
        spans = []; pos = 0                        # char span -> source run
        for r in group:
            spans.append((pos, pos + len(r['t']), r)); pos += len(r['t'])
        def run_at(p):
            for rs, re_, r in spans:
                if rs <= p < re_: return r
            return group[-1]
        repls = []
        for m in rx.finditer(ft):
            tgt = tgt_of.get(m.group(1))
            if not tgt or tgt == e['id'] or tgt in used or n_here[0] >= cap:
                continue
            st, en = m.start(1), m.end(1); base = run_at(st)
            lk = {'kind': 'link', 't': text[st:en], 'target': tgt}
            if base.get('bold'):   lk['bold'] = True
            if base.get('italic'): lk['italic'] = True
            if base.get('v'):      lk['v'] = base['v']
            repls.append((st, en, lk)); used.add(tgt); n_here[0] += 1; count[0] += 1
        if not repls:
            return group
        out = []; last = 0
        def emit_plain(a, b):
            for rs, re_, r in spans:
                lo = max(a, rs); hi = min(b, re_)
                if lo < hi: out.append({**r, 't': text[lo:hi]})
        for st, en, lk in repls:
            if st > last: emit_plain(last, st)
            out.append(lk); last = en
        if last < len(text): emit_plain(last, len(text))
        return out
    def process_entry(e):
        used = set()                               # targets already linked in this entry
        for b in e['blocks']:
            for r in b['runs']:
                if r.get('kind') == 'link' and r.get('target'):
                    used.add(r['target'])          # don't duplicate an existing see-also link
        n_here = [0]
        for b in e['blocks']:
            newruns = []; runs = b['runs']; i = 0
            while i < len(runs):
                if runs[i].get('kind') != 'text':
                    newruns.append(runs[i]); i += 1; continue
                j = i
                while j < len(runs) and runs[j].get('kind') == 'text': j += 1
                newruns.extend(process_group(runs[i:j], e, used, n_here)); i = j
            b['runs'] = newruns
    for s in sections:
        if s.get('kind') != 'glossary':
            continue
        for e in s['entries']:
            process_entry(e)
    return count[0]


def apply_versions(allsecs, pack):
    """Turn the parser's `red` flags into version tags. Runs added in the newest
    version get v=<newest>; entries with a red title -> newIn; entries with new
    body text -> updatedIn. Returns the versions manifest + a 'what's new' index.

    With a single version there is nothing to diff against, so no run is tagged.
    """
    versions = [{'v': v['v'], 'date': v['date']} for v in pack.versions]
    latest = versions[-1]['v'] if len(versions) > 1 else None
    def tag(runs):
        for r in runs:
            if r.pop('red', False) and latest:
                r['v'] = latest
    for s in allsecs:
        for b in s.get('intro', []):
            tag(b['runs'])
        for e in s.get('entries', []):
            if e.get('titleRuns'):
                tag(e['titleRuns'])
            for b in e['blocks']:
                tag(b['runs'])
            new_body = any(r.get('v') == latest for b in e['blocks'] for r in b['runs']) if latest else False
            if latest and e.pop('_new', False):
                e['newIn'] = latest
            elif latest and new_body:
                e['updatedIn'] = latest
            else:
                e.pop('_new', None)
    # what's-new index (per version): new entries + updated entries
    whatsnew = {}
    for s in allsecs:
        for e in s.get('entries', []):
            v = e.get('newIn') or e.get('updatedIn')
            if not v:
                continue
            wn = whatsnew.setdefault(v, {'new': [], 'updated': []})
            item = {'id': e['id'], 'title': e['title'], 'sid': s['id'], 'sec': s['title'], 'num': s['num']}
            (wn['new'] if e.get('newIn') else wn['updated']).append(item)
    return versions, whatsnew

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/assemble.py <lang>', file=sys.stderr)
        return 2
    pack = langpack.load(sys.argv[1])
    lang = pack.code
    if not os.path.exists(pack.nodes_path):
        raise langpack.PackError(
            f'the parsed nodes for "{lang}" are missing (data/_nodes_{lang}.json).\n'
            f'  Run the whole pipeline instead:  python tools/ingest.py {lang}')
    nodes = json.load(open(pack.nodes_path, encoding='utf-8'))
    images_path = pack.images_path(os.path.join(langpack.ROOT, 'assets', 'img'))
    if not os.path.exists(images_path) and (pack.figures or pack.montages):
        # Without the manifest every figure would quietly vanish from the page while
        # the run still reported success — so refuse rather than half-build.
        raise langpack.PackError(
            f'the figure manifest for "{lang}" is missing '
            f'(assets/img/images_{lang}.json), but the pack declares '
            f'{len(pack.figures)} figure(s) and {len(pack.montages)} montage(s).\n'
            f'  Render them first:  python tools/render_images.py {lang}\n'
            f'  Or just run the whole pipeline:  python tools/ingest.py {lang}')
    images = json.load(open(images_path, encoding='utf-8')) if os.path.exists(images_path) else {}
    intro, sections, title_index = assemble(pack, nodes, images)
    allsecs = [intro] + sections
    versions, whatsnew = apply_versions(allsecs, pack)
    links = linkify(allsecs, title_index, pack)
    autolinks = autolink(allsecs, title_index, pack)
    data = {'lang': lang, 'sections': allsecs, 'versions': versions, 'whatsnew': whatsnew}
    json.dump(data, open(pack.data_path, 'w', encoding='utf-8'), ensure_ascii=False)
    # ---- report ----
    print(f'[{lang}] sections: {len(allsecs)}  cross-links: {links}  auto-links: {autolinks}  versions: {[v["v"] for v in versions]}')
    for v, wn in whatsnew.items():
        print(f'  what\'s new in v{v}: {len(wn["new"])} new entries, {len(wn["updated"])} updated')
    if len(versions) > 1 and not whatsnew:
        print(f'  [warn] v{versions[-1]["v"]} produced no "What\'s New" entries. That diff comes '
              f'from the dark-red text the publisher prints for additions; if this edition does '
              f'not use red, the section will not appear.')
    tot = sum(len(s['entries']) for s in allsecs)
    print(f'  TOTAL entries: {tot}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
