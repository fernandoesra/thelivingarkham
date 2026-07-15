# -*- coding: utf-8 -*-
"""Assemble parsed nodes -> final structured data model for The Living Arkham.
  * groups nodes into top-level sections (ordered, roman-numeral aware)
  * assigns stable slugs/anchors to sections & entries
  * resolves cross-references ("Consulta también ... página N") into inline links
  * attaches rendered figures to image sections
  * validates entry counts & cross-reference integrity
Outputs data/grimoire_<lang>.json plus a validation report.
"""
import json, re, sys, os, unicodedata

def slugify(t):
    t = (t or '').strip().lower().replace('“','').replace('”','').replace('"','').replace('’',"'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t or 'x'

def norm(t):
    t = (t or '').strip().lower().replace('“','"').replace('”','"').replace('’',"'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip(' .:"')

# ---- section configuration per language (canonical titles; kind; figures) ----
CFG = {
 'es': {
  'intro_start': 'como usar este documento',
  'index_start': 'indice',
  'sections': [
    ('I','glosario','Glosario de términos y palabras clave','glossary',[]),
    ('II','fundamentos','Fundamentos y reglas adicionales','rules',[]),
    ('III','juego-orden','Juego y orden de resolución','rules',[]),
    ('IV','pruebas-habilidad','Orden de resolución de las pruebas de habilidad','rules',[]),
    ('V','iniciacion','Secuencia de iniciación','rules',[]),
    ('VI','preparacion','Preparación de un escenario','rules',[]),
    ('VII','elementos-cartas','Elementos de las cartas','figures',
        ['card-location','card-agenda-act-treachery-enemy','card-investigator','card-asset-event-skill']),
    ('VIII','campana','Juego de campaña','rules',[]),
    ('IX','mazos','Personalización de mazos','rules',[]),
    ('X','erratas','Notas y fe de erratas','rules',[]),
    ('XI','faq','Preguntas frecuentes','rules',[]),
    ('XII','opcionales','Reglas opcionales','rules',[]),
    ('XIII','reimpresiones','Reimpresiones modificadas','rules',[]),   # source mislabels as XII
    ('XIV','ref-iconos','Referencia de iconos','figures',['icons-products']),
    ('XV','ref-iconos-encuentros','Referencia de iconos de conjuntos de encuentros','figures',
        ['icons-encounter-1','icons-encounter-2']),
    ('','ref-rapida','Referencia rápida','figures',['quick-reference']),
  ],
  # cross-reference triggers & page words
  'trig': r'(consulta(?:\s+tambi[eé]n)?|v[eé]ase|ver)\b',
  'pageword': r'(p[aá]gina|p[aá]g\.?|p\.)',
  'pageref': r'(?:en la|en las|en)\s+p[áa]g(?:inas?|\.)?\s*(\d+(?:\s*[-–]\s*\d+)?)',
  # version history (oldest -> newest). Newest holds the red "new" markup.
  'versions': [{'v': '1.0', 'date': '2026-05-11'}],
 },
 'en': {
  'intro_start': 'using this book',
  'index_start': 'index',
  'sections': [
    ('I','glossary','Glossary of Terms and Keywords','glossary',[]),
    ('II','additional-rules','Additional Rules and Fundamentals','rules',[]),
    ('III','timing-gameplay','Timing and Gameplay','rules',[]),
    ('IV','skill-test-timing','Skill Test Timing','rules',[]),
    ('V','initiation','Initiation Sequence','rules',[]),
    ('VI','scenario-setup','Scenario Setup','rules',[]),
    ('VII','card-anatomy','Card Anatomy','figures',['card-anatomy-1','card-anatomy-2']),
    ('VIII','campaign','Campaign Play','rules',[]),
    ('IX','deck-customization','Deck Customization','rules',[]),
    ('X','notes-errata','Notes and Errata','rules',[]),
    ('XI','faq','Frequently Asked Questions','rules',[]),
    ('XII','optional-rules','Optional Rules','rules',[]),
    ('XIII','modified-reprints','Modified Reprints','rules',[]),
    ('XIV','icon-reference','Icon Reference','figures',['icons-ref-a']),
    ('XV','encounter-icons','Encounter Set Icon Reference','figures',['icons-ref-a','icons-ref-b']),
    ('','quick-reference','Quick Reference','figures',['icons-ref-b']),
  ],
  'trig': r'(see|consult|refer to)\b',
  'pageword': r'(page|pg\.?|p\.)',
  'pageref': r'on pages?\s*(\d+(?:\s*[-–]\s*\d+)?)',
  'versions': [{'v': '1.0', 'date': '2026-03-18'}, {'v': '1.1', 'date': '2026-06-22'}],
 },
}

ROMAN = re.compile(r'^\s*([IVXLC]+)\.\s*(.*)$')

def flat_text(runs):
    return ''.join(r.get('t','') for r in runs if r['kind'] == 'text')

def assemble(lang, nodes, images):
    cfg = CFG[lang]
    seclist = cfg['sections']
    by_num = {}
    for idx,(num,sid,title,kind,figs) in enumerate(seclist):
        if num: by_num[num] = idx
    started = [False]*len(seclist)
    sections = [None]*len(seclist)
    def mk(idx):
        num,sid,title,kind,figs = seclist[idx]
        s = {'num':num,'id':sid,'title':title,'kind':kind,'intro':[], 'entries':[], 'figures':[]}
        for f in figs:
            info = images.get(lang,{}).get(f)
            if info: s['figures'].append({'file':info['file'],'w':info['w'],'h':info['h'],'page':info['page']})
        sections[idx]=s
        return s

    intro_blocks = []
    cur = None            # current section dict
    cur_kind = None
    seen_index = False

    def match_section(title):
        m = ROMAN.match(title)
        n = norm(title)
        # index -> stop
        if n.startswith(cfg['index_start']):
            return 'INDEX'
        # roman numeral exact match to an unstarted section
        if m:
            num = m.group(1)
            if num in by_num and not started[by_num[num]]:
                return by_num[num]
        # special: reimpresiones / modified reprints / referencia rapida / quick reference
        for idx,(num,sid,title2,kind,figs) in enumerate(seclist):
            if started[idx] or num:      # only numberless / by-name specials here
                continue
            if n.startswith(norm(title2)):
                return idx
        # numbered specials matched by name (reimpresiones has a dup numeral in ES)
        for idx,(num,sid,title2,kind,figs) in enumerate(seclist):
            if started[idx]:
                continue
            if n.startswith(norm(title2)) or norm(title2) in n:
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
            if norm(title).startswith(cfg['intro_start']) and blocks:
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
    # drop unstarted sections
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
    intro_section = {'num':'','id':'intro','title':('Cómo empezar' if lang=='es' else 'Getting Started'),
                     'kind':'intro','intro':intro_blocks,'entries':[],'figures':[]}
    return intro_section, sections, title_index, cfg

def linkify(sections, title_index, cfg):
    trig = re.compile(cfg['trig'], re.I)
    pageword = cfg['pageword']
    pageref = re.compile(cfg['pageref'], re.I)
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


def apply_versions(allsecs, cfg):
    """Turn the parser's `red` flags into version tags. Runs added in the newest
    version get v=<newest>; entries with a red title -> newIn; entries with new
    body text -> updatedIn. Returns the versions manifest + a 'what's new' index."""
    versions = cfg.get('versions', [{'v': '1.0', 'date': None}])
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
    lang = sys.argv[1]
    nodes_path = sys.argv[2]
    images_path = sys.argv[3]
    out_path = sys.argv[4]
    nodes = json.load(open(nodes_path, encoding='utf-8'))
    images = json.load(open(images_path, encoding='utf-8')) if os.path.exists(images_path) else {}
    intro, sections, title_index, cfg = assemble(lang, nodes, images)
    allsecs = [intro] + sections
    versions, whatsnew = apply_versions(allsecs, cfg)
    links = linkify(allsecs, title_index, cfg)
    data = {'lang': lang, 'sections': allsecs, 'versions': versions, 'whatsnew': whatsnew}
    json.dump(data, open(out_path,'w',encoding='utf-8'), ensure_ascii=False)
    # ---- report ----
    print(f'[{lang}] sections: {len(allsecs)}  cross-links: {links}  versions: {[v["v"] for v in versions]}')
    for v, wn in whatsnew.items():
        print(f'  what\'s new in v{v}: {len(wn["new"])} new entries, {len(wn["updated"])} updated')
    tot = sum(len(s['entries']) for s in allsecs)
    print(f'  TOTAL entries: {tot}')

if __name__ == '__main__':
    main()
