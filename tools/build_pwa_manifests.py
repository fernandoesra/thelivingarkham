#!/usr/bin/env python3
"""Generate the three lists the service worker (sw.js) reads.

  sw-shell.json  — the light app SHELL: css/js/fonts/icons/manifest + the small registries
                   (languages/releases/ub) + every language's ui/lang/ub/flag. ~2 MB. Cached
                   on SW install so the app opens offline in any language, nothing heavy.
  sw-text.json   — the rules CONTENT (grimoire/faq/nodes/taboos data, all languages). ~8 MB.
                   NOT auto-cached; the footer "download → rules" button caches it on demand
                   (and it also caches as you read, via stale-while-revalidate).
  sw-assets.json — every card/plate IMAGE the site can show. Big (100+ MB). Cached only by the
                   "download → everything" button.

Re-run this whenever content is added/removed (new language, new data file, new card images),
then bump SW_VERSION in sw.js so clients pick up the new lists. See tools/other/instructions.md §7.

    python tools/build_pwa_manifests.py
"""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

def rel(p): return p.as_posix()

def under(d, exts):
    out = []
    base = Path(d)
    if not base.exists(): return out
    for p in base.rglob('*'):
        if not p.is_file(): continue
        rp = p.as_posix()
        # skip source material and build junk that is never served to a browser
        if any(seg in rp for seg in ('/source', '/templates/', '/fonts/')): continue
        if p.name in ('desktop.ini', '_contact_sheet.png'): continue
        if p.suffix.lower() in exts:
            out.append(rp)
    return out

lang_codes = sorted(p.name for p in Path('langs').iterdir()
                    if p.is_dir() and not p.name.startswith('_'))

# small registries the app boots from -> they belong in the light shell, not the rules download
REGISTRIES = ['data/languages.json', 'data/releases.json', 'data/ub.json']

# ---- light shell (auto-precached on install) ----
shell = ['./']
shell += [rel(p) for p in sorted(Path('css').glob('*.css'))]
shell += [rel(p) for p in sorted(Path('js').glob('*.js'))]
shell += [rel(p) for p in sorted(Path('assets/fonts').glob('*.woff2'))]
shell += ['manifest.webmanifest',
          'assets/favicon.svg', 'assets/favicon-32.png', 'assets/favicon-180.png',
          'assets/icon-192.png', 'assets/icon-512.png', 'assets/icon-maskable-512.png',
          'assets/eldersign.svg',
          # small inline brand mark shown with the FAQ's Archivos de Arkham additions (rules text) —
          # 11 KB, so it rides in the light shell and renders offline for rules-only downloaders too
          'assets/img/archivos-de-arkham-logo-libro.png']
shell += [r for r in REGISTRIES if Path(r).exists()]
for code in lang_codes:                       # every language's UI, so it opens offline in any
    for f in ('ui.json', 'lang.json', 'ub.json', 'flag.svg'):
        p = Path('langs', code, f)
        if p.exists(): shell.append(p.as_posix())
shell = [u for u in shell if u == './' or Path(u).exists()]

# ---- rules content (download -> rules): every data/*.json except the shell registries ----
text = [rel(p) for p in sorted(Path('data').glob('*.json')) if rel(p) not in REGISTRIES]

# ---- every servable image / card face (download -> everything) ----
IMG = {'.webp', '.png', '.jpg', '.jpeg', '.svg', '.avif'}
assets = []
for d in ('assets/ub', 'assets/taboo', 'assets/img', 'assets/products',
          'assets/faqsets', 'assets/icons'):
    assets += under(d, IMG | {'.woff2'})       # card-face fonts live beside the plates
assets += ['assets/general_banner_01.webp']
assets = sorted(set(u for u in assets if Path(u).exists()) - set(shell) - set(text))

Path('sw-shell.json').write_text(json.dumps(shell, ensure_ascii=False, indent=0), encoding='utf-8')
Path('sw-text.json').write_text(json.dumps(text, ensure_ascii=False, indent=0), encoding='utf-8')
Path('sw-assets.json').write_text(json.dumps(assets, ensure_ascii=False, indent=0), encoding='utf-8')
old = Path('sw-precache.json')                 # superseded by the shell/text split
if old.exists(): old.unlink()

def mb(urls): return sum(Path(u).stat().st_size for u in urls if u != './' and Path(u).exists()) / 1e6
print(f'sw-shell.json  : {len(shell):4d} files  ~{mb(shell):6.1f} MB  (light shell, auto)')
print(f'sw-text.json   : {len(text):4d} files  ~{mb(text):6.1f} MB  (rules, download)')
print(f'sw-assets.json : {len(assets):4d} files  ~{mb(assets):6.1f} MB  (images, download)')
