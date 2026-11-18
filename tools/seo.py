#!/usr/bin/env python3
"""Give every chapter of the site its own address: the pages search engines read.

The app is one page, index.html, that routes itself in the browser. Until 1.8.0 the route
lived in the URL hash (#es/glosario), and a search engine never reads a hash, so to Google
the whole site, in every language, was ONE page: the home page, rendered in whatever language
its crawler's browser asked for. This script writes a real file for every address the app can
show, so each one can be found, indexed and shared on its own:

    <lang>/index.html              a language's home page          /es/
    <lang>/<chapter>/index.html    one chapter                     /es/glosario/
                                   (an entry is the fragment:      /es/glosario/#<entry-id>)
    sitemap.xml                    every indexable address, with its language alternates
    index.html                     only its marked <head> block (seo:begin … seo:end)

Each page is index.html itself. Its own app boots from it exactly as from the root. Only the
following are made per page:
  - <html lang>, and <base href> pointing back at the app root ("../" or "../../");
  - the seo:begin/seo:end block: title, description, canonical or noindex, hreflang
    alternates, Open Graph / Twitter share tags and, on home pages, schema.org WebSite;
  - the static interface strings (data-i18n*), in the page's language, so a crawler that does
    not run JavaScript does not read a German chapter inside a Spanish frame;
  - the sidebar, as plain links to every chapter (the app replaces it with its own buttons);
  - the chapter's text inside <main>, in the app's own markup and classes, so the first paint
    already looks like the page the app is about to draw over it.

Which pages are indexable. A language with books: every chapter. A language with only an
interface (uiOnly) gets its home page indexed. Its chapters exist so its links and reloads
keep working, but they are noindex: each one only says the book is not in that language, and
hundreds of near-empty pages would cost the site more than they bring.

THIS MIRRORS js/app.js. The section list per language is the app's, rebuilt here:
normalizeData (the "What's New" chapter), mergeFaq (the FAQ chapter-1 shelf), bookShell
(a uiOnly language's borrowed shelf), routeHref (the addresses), navGroups (the shelf
order), setDocMeta (the title). A change to any of those must be made here too, or a
chapter the app links to has no file and its reload is a 404.

Run it after anything that changes what the pages carry: a content build (ingest.py runs
it at the end), an edit to index.html, a ui.json string, a language added or removed.

    python tools/seo.py            write every page, the sitemap and index.html's block
    python tools/seo.py --check    write nothing; exit 1 and list what is out of date
"""
import argparse
import copy
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent

# The canonical origin. Every canonical, alternate, og:url and sitemap entry is written
# against it, so a mirror or a fork served elsewhere still points search engines at the
# original. Bare domain, no www: the other three names 301 here (see deploy.md).
SITE = 'https://thelivingarkham.com'

# The site's own name. It is a proper name and stays in English everywhere, as the header
# in index.html and the landing page in js/app.js already print it.
BRAND = 'The Living Arkham'

# The share image (tools/og_image.py), 1200x630, the size every network crops to.
OG_IMAGE = ('assets/og-image.jpg', 1200, 630)

GEN_MARK = '<meta name="generator" content="tools/seo.py">'
DESC_MAX = 158


def esc(s):
    return html.escape(s or '', quote=True)


def uri(s):
    """encodeURIComponent, which is what js/app.js routeHref() uses."""
    return quote(s, safe="-_.!~*'()")


def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))


# ---------------------------------------------------------------- the app, rebuilt

class Site:
    def __init__(self):
        self.reg = load('data/languages.json')
        self.langs = self.reg['languages']
        self.default = self.reg.get('default')
        self.byc = {L['code']: L for L in self.langs}
        self.packs = {L['code']: load(L['ui']) for L in self.langs}
        self._shelf = {}

    # js/app.js chainOf / pick / t
    def chain(self, code):
        seen, out, c = set(), [], code
        while c and c not in seen:
            seen.add(c)
            out.append(c)
            c = (self.packs.get(c) or {}).get('fallback')
        if self.default and self.default not in seen:
            out.append(self.default)
        return out

    def pick(self, code, group, key):
        for c in self.chain(code):
            g = (self.packs.get(c) or {}).get(group) or {}
            v = g.get(key)
            if v is not None and v != '':
                return v
        return None

    def t(self, code, key):
        v = self.pick(code, 'strings', key)
        return key if v is None else v

    # js/app.js latestInfo / cmpV / langsAhead
    @staticmethod
    def latest_info(g):
        vs, wn = g.get('versions') or [], g.get('whatsnew')
        if len(vs) < 2 or not wn:
            return None
        for v in reversed(vs):
            if wn.get(v['v']):
                return v
        return None

    @staticmethod
    def cmp_v(a, b):
        x, y = str(a or '').split('.'), str(b or '').split('.')
        for i in range(max(len(x), len(y))):
            p = int(x[i]) if i < len(x) and x[i].isdigit() else 0
            q = int(y[i]) if i < len(y) and y[i].isdigit() else 0
            if p != q:
                return -1 if p < q else 1
        return 0

    def langs_ahead(self, code, corpus=None):
        vf = 'faqV' if corpus == 'faq1' else 'v'
        me = (self.byc.get(code) or {}).get(vf)
        if not me:
            return []
        return [L for L in self.langs
                if L['code'] != code and L.get(vf) and self.cmp_v(L[vf], me) > 0]

    # js/app.js bookLangFor
    def book_lang_for(self, code):
        for c in self.chain(code):
            if (self.byc.get(c) or {}).get('data'):
                return c
        d = self.byc.get(self.default)
        if d and d.get('data'):
            return d['code']
        for L in self.langs:
            if L.get('data'):
                return L['code']
        return None

    def has_book(self, code):
        return bool(self.byc[code].get('data'))

    def shelf(self, code):
        """The language's sections, in the app's order, after the app's own reshaping."""
        if code in self._shelf:
            return self._shelf[code]
        reg = self.byc[code]
        if reg.get('data'):
            g = copy.deepcopy(load(reg['data']))
            # normalizeData: the "What's New" chapter, second on the shelf
            if (self.latest_info(g) or self.langs_ahead(code)) and \
                    not any(s['id'] == 'novedades' for s in g['sections']):
                g['sections'].insert(1, {
                    'num': '', 'key': 'whatsnew', 'id': 'novedades', 'kind': 'whatsnew',
                    'group': 'grimoire', 'title': self.pick(code, 'strings', 'news') or "What's New",
                    'intro': [], 'entries': []})
            for s in g['sections']:
                s.setdefault('corpus', 'grimoire')
            # mergeFaq: the FAQ chapter 1 shelf, after the grimoire's
            go = list(g.get('groupOrder') or ['resources', 'grimoire', 'aids'])
            faq = load(reg['faqData']) if reg.get('faqData') and (ROOT / reg['faqData']).exists() else None
            if faq:
                fsecs = []
                for s in faq['sections']:
                    s = dict(s, corpus='faq1')
                    s.setdefault('group', 'chapter1')
                    fsecs.append(s)
                if self.latest_info(faq) and not any(x['id'] == 'faq-novedades' for x in fsecs):
                    fsecs.insert(0, {
                        'num': '', 'key': 'faq-whatsnew', 'id': 'faq-novedades', 'kind': 'whatsnew',
                        'group': 'chapter1', 'corpus': 'faq1',
                        'title': self.pick(code, 'strings', 'news') or "What's New",
                        'intro': [], 'entries': []})
                if 'chapter1' not in go:
                    gi = go.index('grimoire') + 1 if 'grimoire' in go else len(go)
                    go.insert(gi, 'chapter1')
                g['sections'] += fsecs
            out = {'sections': g['sections'], 'groupOrder': go, 'nobook': None}
        else:
            # bookShell: the same chapters, ids and titles as the language it borrows from
            src = self.book_lang_for(code)
            if not src:
                raise SystemExit(f'seo: {code} has no book and nothing to borrow one from')
            b = self.shelf(src)
            out = {'sections': [{'num': s.get('num', ''), 'key': s.get('key'), 'id': s['id'],
                                 'title': s.get('title', ''), 'kind': s.get('kind'),
                                 'group': s.get('group'), 'corpus': s.get('corpus'),
                                 'intro': [], 'entries': []} for s in b['sections']],
                   'groupOrder': b['groupOrder'], 'nobook': src}
        for s in out['sections']:
            if not re.fullmatch(r'[A-Za-z0-9_-]+', s['id']):
                raise SystemExit(f'seo: {code} chapter id {s["id"]!r} is not a safe folder name')
        # findEntry, as a table: any id the app can route to -> (chapter, entry)
        idx = {}
        for s in out['sections']:
            idx.setdefault(s['id'], (s['id'], None))
            for e in s.get('entries') or []:
                idx.setdefault(e['id'], (s['id'], e['id']))
                for bl in e.get('blocks') or []:
                    if bl.get('id'):
                        idx.setdefault(bl['id'], (s['id'], bl['id']))
        out['index'] = idx
        self._shelf[code] = out
        return out

    # js/app.js routeHref, relative to the app root
    def href(self, code, target=''):
        sh = self.shelf(code)
        home = sh['sections'][0]['id']
        sid, eid = sh['index'].get(target, (target, None)) if target else ('', None)
        h = uri(code) + '/' + (uri(sid) + '/' if sid and sid != home else '')
        return h + ('#' + uri(eid) if eid else '')

    def url(self, code, sid=None):
        return SITE + '/' + self.href(code, sid or '')

    # js/app.js navGroups
    def groups(self, code):
        sh, by, out = self.shelf(code), {}, []
        for s in sh['sections']:
            g = s.get('group') or ''
            if g not in by:
                by[g] = {'id': g, 'items': []}
                out.append(by[g])
            by[g]['items'].append(s)
        order = sh['groupOrder']
        out.sort(key=lambda g: -1 if not g['id'] else (order.index(g['id']) if g['id'] in order else 99))
        return out


# ---------------------------------------------------------------- text

def plain(site, code, runs):
    out = []
    for r in runs or []:
        k = r.get('kind')
        if k in ('text', 'link', 'adbcard'):
            out.append(r.get('t') or '')
        elif k == 'icon':
            out.append(site.pick(code, 'icons', r.get('name')) or r.get('name') or '')
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def runs_html(site, code, runs):
    """js/app.js runsHTML, reduced to what a reader without the app needs."""
    h = []
    for r in runs or []:
        k = r.get('kind')
        if k == 'icon':
            lbl = site.pick(code, 'icons', r.get('name')) or r.get('name')
            h.append(f'<i class="ico ico-{esc(r.get("name"))}" title="{esc(lbl)}"></i>')
            continue
        if k == 'seticon':
            lbl = r.get('pn') or site.t(code, 'faqseticon')
            h.append(f'<i class="ico tla-seticon" role="img" aria-label="{esc(lbl)}" title="{esc(lbl)}"></i>')
            continue
        if k == 'pageref':
            op = site.t(code, 'origpage')
            h.append(f'<span class="tla-pageref" title="{esc(op)} {esc(r.get("n"))}">'
                     f'({esc(op)} {esc(r.get("n"))})</span>')
            continue
        t = esc(r.get('t') or '')
        if r.get('bold'):
            t = f'<b>{t}</b>'
        if r.get('italic'):
            t = f'<i>{t}</i>'
        if k == 'link' and r.get('target') in site.shelf(code)['index']:
            t = f'<a class="xref" href="{esc(site.href(code, r["target"]))}">{t}</a>'
        h.append(t)
    return ''.join(h)


def blocks_html(site, code, blocks):
    """js/app.js blocksHTML: paragraphs, bullet lists, symbol rows, small tables."""
    h, i = [], 0
    blocks = blocks or []
    while i < len(blocks):
        b = blocks[i]
        if b.get('type') == 'bullet':
            h.append('<ul class="tla-bul">')
            while i < len(blocks) and blocks[i].get('type') == 'bullet':
                lv = 'l2' if blocks[i].get('level') == 2 else 'l1'
                h.append(f'<li class="{lv}">{runs_html(site, code, blocks[i].get("runs"))}</li>')
                i += 1
            h.append('</ul>')
            continue
        if b.get('type') == 'sym':
            h.append(f'<div class="tla-sym">{runs_html(site, code, b.get("runs"))}</div>')
        elif b.get('type') == 'table':
            h.append('<div class="tla-tablewrap"><table class="tla-table">')
            if b.get('head'):
                h.append('<thead><tr>' + ''.join(f'<th>{esc(c)}</th>' for c in b['head']) + '</tr></thead>')
            h.append('<tbody>' + ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in row) + '</tr>'
                                         for row in b.get('rows') or []) + '</tbody></table></div>')
        else:
            idattr = f' id="e-{esc(b["id"])}"' if b.get('id') else ''
            h.append(f'<p class="tla-p"{idattr}>{runs_html(site, code, b.get("runs"))}</p>')
        i += 1
    return ''.join(h)


def first_text(site, code, s):
    for b in s.get('intro') or []:
        p = plain(site, code, b.get('runs'))
        if p:
            return p
    for e in s.get('entries') or []:
        for b in e.get('blocks') or []:
            p = plain(site, code, b.get('runs'))
            if p:
                return p
    return ''


def clip(s, n=DESC_MAX):
    s = re.sub(r'\s+', ' ', s or '').strip()
    if len(s) <= n:
        return s
    cut = s[:n - 1].rsplit(' ', 1)[0].rstrip(' ,;:.—–-')
    return cut + '…'


# ---------------------------------------------------------------- pages

class Page:
    def __init__(self, code, s, home):
        self.code, self.s, self.home = code, s, home
        self.sid = None if home else s['id']


def page_title(site, p):
    if p.home or not p.s.get('group') or site.t(p.code, 'doctitlesec') == 'doctitlesec':
        return site.t(p.code, 'doctitle')
    return (site.t(p.code, 'doctitlesec').replace('{sec}', p.s.get('title') or '')
            .replace('{shelf}', site.t(p.code, 'grp' + p.s['group'])))


def page_desc(site, p):
    if p.home:
        return clip(site.t(p.code, 'docdesc'), 400)
    blurb = site.pick(p.code, 'blurbs', p.s.get('key')) or ''
    text = first_text(site, p.code, p.s)
    d = blurb
    if text and len(d) < 110:
        d = (d + ' ' + text).strip()
    return clip(d or site.t(p.code, 'docdesc'))


def indexable(site, p):
    return site.has_book(p.code) or p.home


def alternates(site, p):
    """hreflang: the same page in every language that has it as its own indexable page."""
    if p.home:
        alts = [(L['code'], site.url(L['code'])) for L in site.langs]
        return alts + [('x-default', SITE + '/')]
    alts = []
    for L in site.langs:
        if not site.has_book(L['code']):
            continue
        m = next((x for x in site.shelf(L['code'])['sections'] if x.get('key') == p.s.get('key')), None)
        if m:
            alts.append((L['code'], site.url(L['code'], m['id'])))
    if len(alts) < 2:
        return []
    # x-default, for a reader whose language is none of these: the one the default pack
    # itself falls back to (the language every pack's missing strings come from).
    fb = site.book_lang_for((site.packs.get(site.default) or {}).get('fallback') or site.default)
    xd = next((u for c, u in alts if c == fb), alts[0][1])
    return alts + [('x-default', xd)]


def og_locale(site, code):
    loc = (site.packs.get(code) or {}).get('locale') or code
    return loc.replace('-', '_')


def head_block(site, code, title, desc, url, *, canonical, noindex, alts, website, generated):
    img, w, hgt = OG_IMAGE
    out = ['  <!-- seo:begin — WRITTEN BY tools/seo.py, do not edit by hand: the title, description,',
           '       language alternates and share tags of each page, from the language packs. -->',
           f'  <title>{esc(title)}</title>',
           f'  <meta name="description" content="{esc(desc)}">']
    if generated:
        out.append('  ' + GEN_MARK)
    if noindex:
        out.append('  <meta name="robots" content="noindex, follow">')
    if canonical:
        out.append(f'  <link rel="canonical" href="{esc(url)}">')
    for hl, u in alts:
        out.append(f'  <link rel="alternate" hreflang="{esc(hl)}" href="{esc(u)}">')
    out += [
        '  <meta property="og:type" content="website">',
        f'  <meta property="og:site_name" content="{esc(BRAND)}">',
        f'  <meta property="og:title" content="{esc(title)}">',
        f'  <meta property="og:description" content="{esc(desc)}">',
        f'  <meta property="og:url" content="{esc(url)}">',
        f'  <meta property="og:image" content="{esc(SITE + "/" + img)}">',
        f'  <meta property="og:image:width" content="{w}">',
        f'  <meta property="og:image:height" content="{hgt}">',
        f'  <meta property="og:image:alt" content="{esc(BRAND)}">',
        f'  <meta property="og:locale" content="{esc(og_locale(site, code))}">',
    ]
    for hl, _ in alts:
        if hl not in ('x-default', code):
            out.append(f'  <meta property="og:locale:alternate" content="{esc(og_locale(site, hl))}">')
    out.append('  <meta name="twitter:card" content="summary_large_image">')
    if website:
        ld = {'@context': 'https://schema.org', '@type': 'WebSite', 'name': BRAND,
              'alternateName': 'Living Arkham', 'url': SITE + '/', 'inLanguage': code,
              'description': desc}
        out.append('  <script type="application/ld+json">' +
                   json.dumps(ld, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    out.append('  <!-- seo:end -->')
    return '\n'.join(out)


SEO_RE = re.compile(r'  <!-- seo:begin.*?<!-- seo:end -->', re.S)


def with_head(tpl, block):
    if len(SEO_RE.findall(tpl)) != 1:
        raise SystemExit('seo: index.html must hold exactly one seo:begin … seo:end block')
    return SEO_RE.sub(lambda m: block, tpl, count=1)


def set_html_lang(doc, code, dirn):
    def fix(m):
        tag = re.sub(r'\slang="[^"]*"', f' lang="{esc(code)}"', m.group(0), count=1)
        tag = re.sub(r'\sdir="[^"]*"', '', tag)
        if dirn and dirn != 'ltr':
            tag = tag[:-1] + f' dir="{esc(dirn)}">'
        return tag
    return re.sub(r'<html\b[^>]*>', fix, doc, count=1)


def localize_static(site, code, doc):
    """js/app.js applyStaticStrings, done ahead of time on the page's own markup."""
    n_text = doc.count('data-i18n="')
    n_html = doc.count('data-i18n-html="')
    n_attr = doc.count('data-i18n-attr="')
    done = [0, 0, 0]

    def text(m):
        done[0] += 1
        return m.group(1) + esc(site.t(code, m.group(3))) + m.group(5)
    doc = re.sub(r'(<([a-z0-9]+)\b[^>]*\sdata-i18n="([^"]+)"[^>]*>)([^<]*)(</\2>)', text, doc)

    def rich(m):
        if re.search(r'<' + m.group(2) + r'\b', m.group(4)):
            raise SystemExit(f'seo: data-i18n-html="{m.group(3)}" holds a nested <{m.group(2)}>')
        done[1] += 1
        # The footer's "v1.8.0" is left out: every release bumps it in all eleven packs, and it
        # would rewrite every page here for a number no search engine needs (the app prints it).
        return m.group(1) + re.sub(r'\s*<b>v\d+(\.\d+)+</b>', '', site.t(code, m.group(3))) + m.group(5)
    doc = re.sub(r'(<([a-z0-9]+)\b[^>]*\sdata-i18n-html="([^"]+)"[^>]*>)(.*?)(</\2>)', rich, doc, flags=re.S)

    def attrs(m):
        tag = m.group(0)
        spec = re.search(r'\sdata-i18n-attr="([^"]+)"', tag).group(1)
        for pair in spec.split(','):
            kv = pair.split(':')
            if len(kv) != 2:
                continue
            a, k = kv[0].strip(), kv[1].strip()
            v = esc(site.t(code, k))
            if re.search(r'\s' + re.escape(a) + r'="', tag):
                tag = re.sub(r'(\s' + re.escape(a) + r'=")[^"]*(")', lambda mm: mm.group(1) + v + mm.group(2), tag, count=1)
            else:
                tag = tag[:-1] + f' {a}="{v}">'
        done[2] += 1
        return tag
    doc = re.sub(r'<[a-z0-9]+\b[^>]*\sdata-i18n-attr="[^"]+"[^>]*>', attrs, doc)
    if done != [n_text, n_html, n_attr]:
        raise SystemExit(f'seo: localised {done} of {[n_text, n_html, n_attr]} data-i18n hooks in index.html '
                         '— a hook the patterns here cannot read (nested markup?)')
    return doc


def nav_html(site, code):
    h = []
    for g in site.groups(code):
        if g['id']:
            h.append(f'<h2 class="tla-nav-grp">{esc(site.t(code, "grp" + g["id"]))}</h2>')
        h.append('<ul>')
        for s in g['items']:
            num = f'{esc(s["num"])}. ' if s.get('num') else ''
            h.append(f'<li><a href="{esc(site.href(code, s["id"]))}">{num}{esc(s.get("title"))}</a></li>')
        h.append('</ul>')
    return ''.join(h)


def nobook_html(site, code, s, to):
    reg = site.byc.get(to) or {}
    return ('<aside class="tla-obsolete" role="note">'
            f'<div class="tla-obsolete-tag">{esc(site.t(code, "noticeword"))}</div>'
            f'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">{esc(site.t(code, "secnobook"))}</p>'
            f'<a class="tla-obsolete-go" href="{esc(site.href(to, s["id"]))}" lang="{esc(to)}">'
            f'{esc(site.t(code, "secnobooklink"))} <span aria-hidden="true">→</span></a>'
            f'<span class="tla-sr"> ({esc(reg.get("name") or to)})</span></div></aside>')


def main_html(site, p):
    code, s = p.code, p.s
    nobook = site.shelf(code)['nobook']
    if p.home:
        h = ['<div class="tla-doc tla-landing"><div class="tla-hero"><div class="tla-hero-inner">',
             f'<h1 class="tla-hero-title">{esc(BRAND)}</h1>',
             f'<p class="tla-hero-sub">{esc(site.t(code, "sub"))}</p></div></div>',
             f'<p class="tla-p">{esc(site.t(code, "docdesc"))}</p>']
        if not nobook:
            h.append(blocks_html(site, code, s.get('intro')))
        h.append(f'<h2 class="tla-cards-h">{esc(site.t(code, "browse"))}</h2>')
        for g in site.groups(code):
            items = [x for x in g['items'] if x is not s]
            if not items:
                continue
            if g['id']:
                h.append(f'<h3 class="tla-cards-grp">{esc(site.t(code, "grp" + g["id"]))}</h3>')
            h.append('<ul>')
            for x in items:
                bl = site.pick(code, 'blurbs', x.get('key'))
                h.append(f'<li><a href="{esc(site.href(code, x["id"]))}">{esc(x.get("title"))}</a>'
                         + (f' — {esc(bl)}' if bl else '') + '</li>')
            h.append('</ul>')
        h.append('</div>')
        return ''.join(h)
    num = s.get('num') or ''
    h = ['<div class="tla-doc">',
         f'<div class="tla-crumb">{("· " + esc(num) + " ·") if num else ""} {esc(BRAND)}</div>',
         '<h1 class="tla-h1">' + (f'<span class="tla-rn">{esc(num)}.</span>' if num else '')
         + f'{esc(s.get("title"))}</h1>',
         '<div class="tla-rule"></div>']
    if nobook:
        h.append(nobook_html(site, code, s, nobook))
    else:
        bl = site.pick(code, 'blurbs', s.get('key'))
        if bl and not (s.get('intro') or s.get('entries')):
            h.append(f'<p class="tla-p">{esc(bl)}</p>')
        h.append(blocks_html(site, code, s.get('intro')))
        for e in s.get('entries') or []:
            title = runs_html(site, code, e['titleRuns']) if e.get('titleRuns') else esc(e.get('title'))
            h.append(f'<article class="tla-entry" id="e-{esc(e["id"])}"><h2>{title}</h2>'
                     + blocks_html(site, code, e.get('blocks')) + '</article>')
    h.append('</div>')
    return ''.join(h)


MAIN_EMPTY = '<main class="tla-main" id="tla-main" tabindex="0"></main>'
NAV_RE = re.compile(r'(<nav class="tla-nav" id="tla-nav"[^>]*>)(</nav>)')


def build_page(site, tpl, p, depth):
    code = p.code
    url = site.url(code, p.sid)
    idx = indexable(site, p)
    title, desc = page_title(site, p), page_desc(site, p)
    doc = with_head(tpl, head_block(site, code, title, desc, url, canonical=idx, noindex=not idx,
                                    alts=alternates(site, p) if idx else [], website=p.home and idx,
                                    generated=True))
    doc = set_html_lang(doc, code, site.byc[code].get('dir'))
    if doc.count('<base href="./">') != 1:
        raise SystemExit('seo: index.html must carry exactly one <base href="./">')
    doc = doc.replace('<base href="./">', f'<base href="{"../" * depth}">', 1)
    doc = localize_static(site, code, doc)
    if doc.count(MAIN_EMPTY) != 1 or len(NAV_RE.findall(doc)) != 1:
        raise SystemExit('seo: index.html no longer has the empty <main id="tla-main"> and <nav id="tla-nav"> '
                         'this script fills — update MAIN_EMPTY / NAV_RE')
    doc = doc.replace(MAIN_EMPTY, MAIN_EMPTY[:-7] + main_html(site, p) + '</main>', 1)
    doc = NAV_RE.sub(lambda m: m.group(1) + nav_html(site, code) + m.group(2), doc, count=1)
    return doc


def root_index(site, tpl):
    """The root page: the x-default of every home page. Only its <head> block is ours."""
    code = site.default
    p = Page(code, site.shelf(code)['sections'][0], True)
    alts = alternates(site, p)
    block = head_block(site, code, page_title(site, p), page_desc(site, p), SITE + '/',
                       canonical=False, noindex=False, alts=alts, website=True, generated=False)
    return set_html_lang(with_head(tpl, block), code, site.byc[code].get('dir'))


def sitemap(site, pages):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!-- WRITTEN BY tools/seo.py: every indexable address, with its language alternates. -->',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml">']

    def entry(loc, alts):
        out.append(f'  <url><loc>{esc(loc)}</loc>')
        for hl, u in alts:
            out.append(f'    <xhtml:link rel="alternate" hreflang="{esc(hl)}" href="{esc(u)}"/>')
        out.append('  </url>')
    root_alts = alternates(site, Page(site.default, site.shelf(site.default)['sections'][0], True))
    entry(SITE + '/', root_alts)
    for p in pages:
        if indexable(site, p):
            entry(site.url(p.code, p.sid), alternates(site, p))
    out.append('</urlset>')
    return '\n'.join(out) + '\n'


def plan(site, tpl):
    """Every file this script owns -> its content."""
    files = {}
    pages = []
    for L in site.langs:
        code = L['code']
        secs = site.shelf(code)['sections']
        for i, s in enumerate(secs):
            p = Page(code, s, i == 0)
            pages.append(p)
            rel = f'{code}/index.html' if p.home else f'{code}/{s["id"]}/index.html'
            files[rel] = build_page(site, tpl, p, 1 if p.home else 2)
    files['index.html'] = root_index(site, tpl)
    files['sitemap.xml'] = sitemap(site, pages)
    return files


def owned_on_disk(site):
    """Pages this script wrote before (they carry its generator tag): the stale ones go."""
    found = set()
    for d in ROOT.iterdir():
        if not d.is_dir() or not re.fullmatch(r'[a-z]{2,3}(-[A-Za-z0-9]+)?', d.name):
            continue
        for f in [d / 'index.html', *d.glob('*/index.html')]:
            try:
                if f.is_file() and GEN_MARK in f.read_text(encoding='utf-8'):
                    found.add(f.relative_to(ROOT).as_posix())
            except UnicodeDecodeError:
                pass
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true', help='write nothing; exit 1 if anything is out of date')
    return run(check=ap.parse_args(argv).check)


def run(check=False):
    a = argparse.Namespace(check=check)
    site = Site()
    tpl = (ROOT / 'index.html').read_text(encoding='utf-8')
    files = plan(site, tpl)
    stale = sorted(owned_on_disk(site) - set(files))
    changed = []
    for rel, txt in files.items():
        f = ROOT / rel
        old = f.read_text(encoding='utf-8') if f.exists() else None
        if old != txt:
            changed.append(rel)
            if not a.check:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(txt, encoding='utf-8', newline='\n')
    if not a.check:
        for rel in stale:
            f = ROOT / rel
            f.unlink()
            try:
                f.parent.rmdir()
            except OSError:
                pass
    n_idx = sum(1 for rel in files if rel.endswith('index.html')) - 1
    if a.check:
        if changed or stale:
            for rel in changed:
                print('out of date:', rel)
            for rel in stale:
                print('stale:      ', rel)
            print(f'seo: {len(changed)} out of date, {len(stale)} stale — run: python tools/seo.py')
            return 1
        print(f'seo: all {n_idx} pages, index.html and sitemap.xml are up to date')
        return 0
    print(f'seo: {n_idx} pages; {len(changed)} written, {len(stale)} stale removed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
