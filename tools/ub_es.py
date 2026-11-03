# -*- coding: utf-8 -*-
"""Apply the community Spanish translations to the Ultimatums & Boons viewer.

The viewer shows every card in every language; one not yet officially translated is shown in
English, flagged (tools/ub_merge.py). Until the official Spanish arrives, Rincón Miskatonic
translates some of them — the Grimoire 1.1 additions and the fan-made Cultist Challenges cards.

This step reads those translations from a human-friendly Markdown file
(tools/ub_es_translations.md) and splices each into the SPANISH grimoire in place of its English
fallback: the card then reads in Spanish, is no longer ``pending``, and carries a ``tby``
("translated by") credit the viewer renders as "Traducido por Rincón Miskatonic — a la espera de
traducción oficial.".

Spanish only — every other language keeps the English fallback and its "awaiting translation"
notice. Must run AFTER ub_merge (the pending Spanish cards have to exist to be translated), so
ingest.py calls it there; standalone:

    python tools/ub_es.py

The Markdown is the source of truth and is safe to hand-edit; see its own header for the format.
When an official translation lands, delete that card's block there (it falls back to English +
notice) or replace it. Empty cards (no ES-NOMBRE / ES-TEXTO) are left untranslated.
"""
import json
import os
import re
import sys

import langpack

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ub_es_translations.md')
ICONS_CSS = os.path.join(ROOT, 'css', 'icons.css')
DEFAULT_BY = 'Rincón Miskatonic'
BUCKETS = ('ultimatums', 'boons', 'refractions')
SLUG_RE = re.compile(r'^[a-z][a-z0-9-]+$')          # a real card slug, not a prose heading
# ES-NOMBRE / ES-TEXTO / ES-CAMPAÑA / ES-ESCENARIO / ES-POR  (accent optional on CAMPAÑA)
FIELD_RE = re.compile(r'(?i)^\s*ES[-\s]?(NOMBRE|TEXTO|CAMPA(?:Ñ|N)A|ESCENARIO|POR)\s*:(.*)$')
FIELD_KEY = {'NOMBRE': 'name', 'TEXTO': 'TEXTO', 'CAMPANA': 'campaign',
             'ESCENARIO': 'scenario', 'POR': 'by'}
# Inline markup: [icon] | bold+italic | bold | italic. Bold+italic (card traits like Monster /
# Civilian) is written either ***x***, **_x_** or _**x**_ — all three are accepted and must come
# before the plain **bold** / *italic* branches so the longer match wins.
INLINE_RE = re.compile(
    r'\[([a-z0-9]+)\]'           # 1 [icon]
    r'|\*\*\*(.+?)\*\*\*'        # 2 ***bold+italic***
    r'|\*\*_(.+?)_\*\*'          # 3 **_bold+italic_**
    r'|_\*\*(.+?)\*\*_'          # 4 _**bold+italic**_
    r'|\*\*(.+?)\*\*'            # 5 **bold**
    r'|\*(.+?)\*')               # 6 *italic*


def _ub(data):
    for s in data.get('sections', []):
        if s.get('kind') == 'ultimatums':
            return s
    return None


def _valid_icons():
    """The game-icon names the stylesheet actually defines (ico-<name>), so an unknown token in
    the Markdown is caught rather than emitted as a broken icon."""
    try:
        txt = open(ICONS_CSS, encoding='utf-8').read()
    except OSError:
        return set()
    return set(re.findall(r'\.ico-([a-z0-9]+)\b', txt))


def _parse_inline(text, valid, warn):
    runs, pos = [], 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            runs.append({'kind': 'text', 't': text[pos:m.start()]})
        if m.group(1) is not None:                  # [icon]
            tok = m.group(1)
            if tok in valid:
                runs.append({'kind': 'icon', 'name': tok})
            else:
                warn(f'unknown icon token [{tok}] kept as text')
                runs.append({'kind': 'text', 't': m.group(0)})
        elif m.group(2) is not None or m.group(3) is not None or m.group(4) is not None:
            trait = m.group(2) or m.group(3) or m.group(4)   # bold+italic (***x*** / **_x_** / _**x**_)
            runs.append({'kind': 'text', 't': trait, 'bold': True, 'italic': True})
        elif m.group(5) is not None:                # **bold**
            runs.append({'kind': 'text', 't': m.group(5), 'bold': True})
        else:                                       # *italic*
            runs.append({'kind': 'text', 't': m.group(6), 'italic': True})
        pos = m.end()
    if pos < len(text):
        runs.append({'kind': 'text', 't': text[pos:]})
    return [r for r in runs if not (r.get('kind') == 'text' and not r['t'])]


def _text_to_blocks(text, valid, warn):
    blocks = []
    for para in re.split(r'\n\s*\n', text.strip()):
        bullet = False
        joined = ' '.join(ln.strip() for ln in para.splitlines() if ln.strip())
        if joined.startswith('- '):
            bullet, joined = True, joined[2:].strip()
        if not joined:
            continue
        blk = {'type': 'bullet' if bullet else 'p', 'runs': _parse_inline(joined, valid, warn)}
        blocks.append(blk)
    return blocks


def parse_md(path=None):
    """{slug: {name, TEXTO, campaign?, scenario?, by?}} for every card block with content."""
    path = path or MD
    if not os.path.exists(path):
        return {}
    cards, cur, field, buf = {}, None, None, []

    def flush():
        if cur is not None and buf:
            cur['TEXTO'] = '\n'.join(buf).strip('\n')

    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        if line.startswith('## '):
            flush(); buf = []
            slug = line[3:].strip().split()[0] if line[3:].strip() else ''
            if SLUG_RE.match(slug):
                cur = {}
                cards[slug] = cur
            else:
                cur = None                          # a prose heading, not a card
            field = None
            continue
        s = line.strip()
        if s == '---' or s.startswith('# '):        # a '---' rule or a '# Section' header ends the
            flush(); buf = []; cur = None; field = None   # current card, so its text never swallows
            continue                                      # the section break that follows the last one
        if cur is None:
            continue
        if line.lstrip().startswith('>'):           # English reference, ignored
            continue
        m = FIELD_RE.match(line)
        if m:
            flush(); buf = []
            key = FIELD_KEY[m.group(1).upper().replace('Ñ', 'N')]
            val = m.group(2).strip()
            if key == 'TEXTO':
                field = 'TEXTO'
                if val:
                    buf.append(val)
            else:
                field = None
                cur[key] = val
            continue
        if field == 'TEXTO':
            buf.append(line)
    flush()
    return cards


def build(datadir=None, quiet=False):
    say = (lambda *a, **k: None) if quiet else print
    datadir = datadir or langpack.DATA_DIR
    gpath = os.path.join(datadir, 'grimoire_es.json')
    if not os.path.exists(gpath):
        say('  [ub_es] no Spanish grimoire — skipped')
        return 0
    trans = {s: c for s, c in parse_md().items() if c.get('name') and c.get('TEXTO')}
    if not trans:
        say('  [ub_es] no Spanish translations filled in yet — nothing to apply')
        return 0
    data = json.load(open(gpath, encoding='utf-8'))
    sec = _ub(data)
    if not sec or 'ub' not in sec:
        say('  [ub_es] Spanish has no ultimatums viewer — skipped')
        return 0
    valid = _valid_icons()
    warned = []
    warn = lambda msg: warned.append(msg)
    ub, applied, done = sec['ub'], 0, set()
    for b in BUCKETS:
        for it in ub.get(b, []):
            c = trans.get(it['slug'])
            if not c or it['slug'] in done:
                continue
            it['name'] = c['name']
            it['blocks'] = _text_to_blocks(c['TEXTO'], valid, warn)
            if b == 'refractions':
                if c.get('campaign'):
                    it['campaign'] = c['campaign']
                if c.get('scenario'):
                    it['scenario'] = c['scenario']
                scen, camp = it.get('scenario', ''), it.get('campaign', '')
                sub = f'{scen} ({camp})' if scen and camp else camp or scen
                if sub:
                    it['subtitle'] = [{'kind': 'text', 't': sub}]
            it.pop('pending', None)                 # it reads in Spanish now
            it['tby'] = c.get('by') or DEFAULT_BY
            done.add(it['slug'])
            applied += 1
    json.dump(data, open(gpath, 'w', encoding='utf-8'), ensure_ascii=False)
    missing = sorted(set(trans) - done)
    say(f'  [ub_es] applied {applied} Spanish translation(s)'
        + (f'; not in the viewer: {", ".join(missing)}' if missing else ''))
    for w in warned:
        say(f'    [ub_es warn] {w}')
    return applied


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build()
    return 0


if __name__ == '__main__':
    sys.exit(main())
