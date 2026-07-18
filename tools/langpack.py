# -*- coding: utf-8 -*-
"""Language packs: discovery, loading and validation.

A language pack is a folder under `langs/<code>/` containing everything one
language needs, and nothing about any other language:

    langs/<code>/lang.json    how to read this language's PDF (this file)
    langs/<code>/ui.json      the interface strings (read by the browser)
    langs/<code>/source/      the Grimoire PDFs themselves

Every pipeline script takes a language *code* and asks this module for the
config. Adding a language therefore means adding a folder — no script is ever
edited. Validation is deliberately loud: a malformed pack must fail with a
sentence a non-programmer can act on, never with a traceback or, worse, a
successful run that silently drops content.
"""
import json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANGS_DIR = os.path.join(ROOT, 'langs')
DATA_DIR = os.path.join(ROOT, 'data')
TEMPLATE = '_template'

# The site's default language: the one served when the URL names no language.
# An explicit constant on purpose — never derived from `order`, so that adding a
# pack can not silently make it the default for every visitor.
DEFAULT_LANG = 'es'

# Cross-language section vocabulary. Two packs' sections are "the same chapter"
# when they share a key, which is what the language switcher joins on. Fixed
# on purpose: a free-text key would let packs drift apart silently.
SECTION_KEYS = [
    'glossary', 'additional-rules', 'timing', 'skill-tests', 'initiation', 'setup',
    'card-anatomy', 'campaign', 'deck-building', 'errata', 'faq', 'optional-rules',
    'reprints', 'icon-reference', 'encounter-icons', 'errata-viewer', 'ultimatums',
    'taboos', 'encounter-variation', 'quick-reference',
]

# What the site files a section under. The site is growing past the book — some of what
# it will hold is not a chapter of anything — so a section says which shelf it sits on
# and the navigation reads that, rather than JS carrying a list of keys it has to be
# kept in step with. Fixed vocabulary for the same reason as SECTION_KEYS: the id is
# language-neutral and each pack translates it in its own ui.json, under "grp"+id.
#
# This tuple's ORDER is the shelf order the site shows, top to bottom — Resources sit
# above the Grimoire — independent of where the sections happen to fall in the pack (a
# chapter keeps its number wherever its shelf lands). It is emitted into the data so JS
# reads the order instead of hardcoding it.
SECTION_GROUPS = ('resources', 'grimoire', 'aids')
# How a chapter is read:
#   glossary  A-Z entries          rules     prose entries
#   figures   shown as page images (nothing to read back out)
#   anatomy   picture pages that ARE read back out — the cards stay images, the
#             key and the callouts are rebuilt (tools/card_anatomy.py). The pages
#             come from the chapter's declared figures, so opting in is one word.
#   icons     icon galleries, rebuilt from the page's vector art (icon_reference.py)
#   substitution  prose, plus a table that is drawn rather than written: its rows are
#             rebuilt from the art (substitution.py) and the prose is kept as usual.
#   placeholder  announced, not written yet: the site says a thing is coming and gives
#             it its place in the navigation. It backs onto no PDF heading, so it is the
#             one kind assemble.py must not go looking for.
#   quickref  the one-page reference sheet: an interactive symbol key (classes, skills,
#             chaos tokens — each in its own colour) plus the page image kept for
#             download. The symbols are game-universal, so the app builds them from the
#             icon list; the figure travels as usual.
#   ultimatums  the Ultimatums & Boons card viewer: a gallery built from the
#             "optional-rules" chapter (ultimatums.py reads each bold name + its rule and
#             pairs it with a card picture). Backs onto no heading of its own — it re-reads
#             another chapter — so, like placeholder, assemble.py must not go looking for it.
SECTION_KINDS = ('glossary', 'rules', 'figures', 'anatomy', 'faq', 'icons', 'substitution',
                 'placeholder', 'quickref', 'ultimatums')


class PackError(Exception):
    """A language pack is malformed. The message is aimed at its author."""


def _fail(code, msg):
    raise PackError(f'langs/{code}/lang.json: {msg}')


class Pack(object):
    """One language's configuration, validated and path-resolved.

    Only ever built from a raw dict that `_validate` has already accepted — it
    subscripts required fields directly, so constructing it from unchecked input
    would raise KeyError instead of an author-facing message.
    """

    def __init__(self, code, raw, ui):
        self.code = code
        self.raw = raw
        self.ui = ui
        self.dir = os.path.join(LANGS_DIR, code)
        self.name = raw['name']
        self.label = raw['label']
        self.text_dir = raw.get('dir', 'ltr')
        self.order = raw.get('order', 99)
        self.book = raw['book']
        self.versions = raw['book']['versions']
        self.parse = raw['parse']
        self.sections = raw['sections']
        self.patterns = raw['patterns']
        self.autolink = raw.get('autolink', {})
        self.figures = raw.get('figures', [])
        self.montages = raw.get('montages', [])
        self.inline_symbols = raw.get('inlineSymbols', [])
        self.icon_art = raw.get('iconArt', {'provides': False, 'symbols': {}})

    # ---- paths -------------------------------------------------------------
    @property
    def current(self):
        """The newest version — the one whose PDF is parsed and whose red
        markup becomes the 'what's new' diff."""
        return self.versions[-1]

    @property
    def pdf(self):
        """Absolute path to the newest version's PDF."""
        return os.path.join(self.dir, 'source', self.current['pdf'])

    @property
    def data_path(self):
        return os.path.join(DATA_DIR, f'grimoire_{self.code}.json')

    @property
    def nodes_path(self):
        return os.path.join(DATA_DIR, f'_nodes_{self.code}.json')

    def images_path(self, img_dir):
        return os.path.join(img_dir, f'images_{self.code}.json')

    def has_pdf(self):
        return os.path.exists(self.pdf)

    def require_pdf(self):
        if not self.has_pdf():
            raise PackError(
                f"langs/{self.code}: the PDF for the newest version (v{self.current['v']}) "
                f"is missing.\n  expected: langs/{self.code}/source/{self.current['pdf']}\n"
                f"  Put the file there, or fix the \"pdf\" field of that version in "
                f"langs/{self.code}/lang.json.")
        return self.pdf

    def __repr__(self):
        return f'<Pack {self.code} v{self.current["v"]}>'


# ---- the accent fold used by the autolinker --------------------------------
# Length-preserving on purpose: assemble.py matches regexes against folded text
# and maps the offsets straight back onto the *source* runs, so one folded char
# must equal exactly one source char. A tempting entry like 'ß' -> 'ss' would
# shift every offset after it and corrupt the links silently, which is why this
# table is validated rather than merely documented.
FOLD_FROM = 'áàäâéèëêíìïîóòöôúùüûñçÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑÇ'
FOLD_TO = 'aaaaeeeeiiiioooouuuuncAAAAEEEEIIIIOOOOUUUUNC'


def validate_fold(src=FOLD_FROM, dst=FOLD_TO):
    if len(src) != len(dst):
        raise PackError(
            'the accent-fold table is broken: every character must map to exactly ONE '
            'character, because text offsets in the folded string are mapped back onto '
            'the original. Multi-character expansions (e.g. "ß" -> "ss") are not allowed '
            f'here. Got {len(src)} sources for {len(dst)} targets.')
    return str.maketrans(src, dst)


def fold(s):
    return (s or '').translate(validate_fold()).lower()


def slugify(t):
    t = (t or '').strip().lower().replace('“', '').replace('”', '').replace('"', '').replace('’', "'")
    t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t or 'x'


# ---- discovery / loading ---------------------------------------------------
def _declared_order(code):
    """Read just the `order` field, tolerating anything. Listing the packs must
    not depend on all of them being valid."""
    try:
        with open(os.path.join(LANGS_DIR, code, 'lang.json'), encoding='utf-8') as f:
            return json.load(f).get('order', 99)
    except Exception:
        return 99


def codes():
    """Every language code that has a pack folder, in `order` then code order.

    Deliberately cheap and total: it neither validates nor raises. One broken
    pack must never stop you listing, building or creating the others.
    """
    if not os.path.isdir(LANGS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(LANGS_DIR)):
        if name.startswith('_') or name.startswith('.'):
            continue
        if os.path.exists(os.path.join(LANGS_DIR, name, 'lang.json')):
            out.append(name)
    out.sort(key=lambda c: (_declared_order(c), c))
    return out


def peek_pdf(code):
    """The newest version's PDF path, read without validating the pack.

    inspect_pdf.py exists to help fill a pack in, so it must work on a pack that
    is still half-written — requiring a valid pack here would mean you need the
    answers before you can ask the question.
    """
    path = os.path.join(LANGS_DIR, code, 'lang.json')
    if not os.path.exists(path):
        raise PackError(
            f'there is no language pack for "{code}".\n'
            f'  expected: langs/{code}/lang.json\n'
            f'  Start one with:  python tools/new_lang.py {code}\n'
            f'  Existing packs: {", ".join(codes()) or "(none)"}')
    raw = _read_json(path, code)
    versions = (raw.get('book') or {}).get('versions') or []
    named = versions[-1].get('pdf') if versions else None
    if not named or named.strip().upper().startswith(TODO_MARK):
        raise PackError(
            f'langs/{code}/lang.json does not say which PDF to read yet.\n'
            f'  Put your PDF in langs/{code}/source/, then write its filename into\n'
            f'  "book" -> "versions" -> "pdf".')
    pdf = os.path.join(LANGS_DIR, code, 'source', versions[-1]['pdf'])
    if not os.path.exists(pdf):
        raise PackError(
            f'langs/{code}/source/{versions[-1]["pdf"]} is not there.\n'
            f'  Copy the PDF into langs/{code}/source/, or fix the "pdf" field in '
            f'langs/{code}/lang.json.')
    return pdf


def resolve(only=None):
    """The codes to work on. Raises only if a code you asked for isn't there."""
    cs = codes()
    if not only:
        return cs
    missing = [c for c in only if c not in cs]
    if missing:
        raise PackError(
            f'no language pack for: {", ".join(missing)}.\n'
            f'  Available: {", ".join(cs) or "(none)"}\n'
            f'  Start a new one with:  python tools/new_lang.py {missing[0]}')
    return [c for c in cs if c in only]


_cache = {}


def load(code):
    """Load + validate one pack. Raises PackError with an author-facing message."""
    if code in _cache:
        return _cache[code]
    d = os.path.join(LANGS_DIR, code)
    lang_file = os.path.join(d, 'lang.json')
    ui_file = os.path.join(d, 'ui.json')
    if not os.path.exists(lang_file):
        raise PackError(
            f'there is no language pack for "{code}".\n'
            f'  expected: langs/{code}/lang.json\n'
            f'  Start one with:  python tools/new_lang.py {code}\n'
            f'  Existing packs: {", ".join(codes()) or "(none)"}')
    raw = _read_json(lang_file, code)
    ui = _read_json(ui_file, code) if os.path.exists(ui_file) else None
    if ui is None:
        raise PackError(f'langs/{code}/ui.json is missing — it holds this language\'s '
                        f'interface strings.\n'
                        f'  Copy langs/{DEFAULT_LANG}/ui.json and translate the values, or '
                        f'start the pack over with:  python tools/new_lang.py {code}')
    _validate(code, raw, ui)          # before Pack(), which trusts its input
    pack = Pack(code, raw, ui)
    _cache[code] = pack
    return pack


def _read_json(path, code):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        raise PackError(
            f'{rel} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno}).\n'
            f'  Usually a missing comma, a trailing comma, or an unescaped backslash '
            f'(write \\\\ inside a regex).')


# The template's placeholder marker. The colon matters: plain "TODO" is a real
# word in the languages most likely to be contributed — Spanish "Todos los
# investigadores", Portuguese "Tudo…" — and rejecting a pack for writing its own
# language correctly would be an absurd way to greet a translator.
TODO_MARK = 'TODO:'


def _todos(obj, path=''):
    """Every field still holding a placeholder from the template."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _todos(v, f'{path}.{k}' if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _todos(v, f'{path}[{i}]')
    elif isinstance(obj, str) and obj.strip().upper().startswith(TODO_MARK):
        out.append(path)
    return out


def _validate(code, raw, ui):
    """Check the raw JSON before anything reads a field out of it, so a mistake
    is always a sentence to act on and never a traceback."""
    for key in ('code', 'name', 'label', 'book', 'parse', 'sections', 'patterns'):
        if key not in raw:
            _fail(code, f'missing required field "{key}".')
    # A scaffolded pack validates on shape alone, so it would otherwise build an
    # empty book and put a live button in the header. Refuse while it is a stub.
    todo = _todos(raw)
    if todo:
        listed = ''.join(f'\n    {x}' for x in todo)
        _fail(code, f'{len(todo)} field(s) still say TODO and need filling in:{listed}\n'
                    f'  See README.md -> "Adding a language".')
    if not raw['sections']:
        _fail(code, '"sections" is empty, so there would be nothing to read.\n'
                    f'  Get a starting point with:  python tools/inspect_pdf.py {code} --sections')
    if raw['code'] != code:
        _fail(code, f'"code" is "{raw["code"]}" but the folder is langs/{code}/. They must match.')
    text_dir = raw.get('dir', 'ltr')
    if text_dir not in ('ltr', 'rtl'):
        _fail(code, f'"dir" must be "ltr" or "rtl", got {text_dir!r}.')
    if not isinstance(raw['book'], dict) or 'versions' not in raw['book']:
        _fail(code, '"book" needs a "versions" list.')

    # --- parse anchors (assemble.py reads all three directly)
    parse_cfg = raw['parse']
    if not isinstance(parse_cfg, dict):
        _fail(code, '"parse" must be an object with "introTitle", "introStart" and '
                    f'"indexStart"; got {parse_cfg!r}.')
    for key in ('introTitle', 'introStart', 'indexStart'):
        if key not in parse_cfg:
            _fail(code, f'"parse.{key}" is required. See README.md -> "Adding a language".')

    # --- versions
    vs = raw['book']['versions']
    if not isinstance(vs, list) or not vs:
        _fail(code, '"book.versions" must list at least one version, oldest first, '
                    'e.g. [{"v": "1.0", "date": "2026-01-31", "pdf": "grimoire_de.pdf"}].')
    for v in vs:
        for key in ('v', 'date', 'pdf'):
            if key not in v:
                _fail(code, f'every entry of "book.versions" needs a "{key}" field; got {v!r}.')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(v['date'])):
            _fail(code, f'version {v["v"]}: "date" must be YYYY-MM-DD, got {v["date"]!r}. '
                        f'(The PDF metadata\'s creationDate is the usual source.)')

    # --- sections
    seen_keys, seen_ids = set(), set()
    for s in raw['sections']:
        # "num" is the printed chapter numeral, "" for an unnumbered one. It is
        # required (assemble.py reads it directly) but may legitimately be empty.
        for key in ('num', 'key', 'id', 'title', 'kind'):
            if key not in s:
                _fail(code, f'every section needs a "{key}" field; got {s!r}.\n'
                            f'  (An unnumbered chapter still needs "num": "".)')
        if s['key'] not in SECTION_KEYS:
            _fail(code, f'section "{s["id"]}" has key {s["key"]!r}, which is not one of the '
                        f'shared section keys. Use one of: {", ".join(SECTION_KEYS)}.\n'
                        f'  (The key is how the language switcher finds the same chapter in '
                        f'another language. It is not shown to readers.)')
        if s['key'] in seen_keys:
            _fail(code, f'two sections share the key {s["key"]!r}. Keys must be unique.')
        if s['id'] in seen_ids:
            _fail(code, f'two sections share the id {s["id"]!r}. Ids must be unique — they are URLs.')
        if s['kind'] not in SECTION_KINDS:
            _fail(code, f'section "{s["id"]}" has kind {s["kind"]!r}; must be one of '
                        f'{", ".join(SECTION_KINDS)}.')
        if s.get('group') and s['group'] not in SECTION_GROUPS:
            _fail(code, f'section "{s["id"]}" is in group {s["group"]!r}, which is not one of '
                        f'{", ".join(SECTION_GROUPS)}.\n'
                        f'  (A group is the shelf the site files a section under. Like "key" it '
                        f'is language-neutral — each pack names it in its own ui.json, under '
                        f'"grp{s["group"]}".)')
        if s['kind'] == 'substitution' and not s.get('tableHeading'):
            _fail(code, f'section "{s["id"]}" is "kind": "substitution" but declares no '
                        f'"tableHeading".\n'
                        f'  The table is drawn, not written, so its rows are rebuilt from the '
                        f'page\'s art — but the heading the book prints over it is a string, '
                        f'and strings live here. Copy it exactly as the PDF prints it; the '
                        f'build checks it against the heading standing over the art.')
        if s['id'] != slugify(s['id']):
            _fail(code, f'section id {s["id"]!r} is not URL-safe. Use lowercase letters, '
                        f'digits and hyphens, e.g. {slugify(s["id"])!r}.')
        seen_keys.add(s['key'])
        seen_ids.add(s['id'])

    # --- figures (check the fields before anything reads them)
    figures = raw.get('figures', [])
    for f in figures:
        for key in ('name', 'page'):
            if key not in f:
                _fail(code, f'every entry of "figures" needs a "{key}" field; got {f!r}.')
    declared = {f['name'] for f in figures}
    for s in raw['sections']:
        for fname in s.get('figures', []):
            if fname not in declared:
                _fail(code, f'section "{s["id"]}" lists the figure {fname!r}, but no figure of '
                            f'that name is declared in "figures".\n'
                            f'  Declared: {", ".join(sorted(declared)) or "(none)"}')

    # --- montages
    for m in raw.get('montages', []):
        # "info" is the textual alternative shown behind the figure's "i" button;
        # it is what makes the picture readable to a screen reader, so it is required.
        for key in ('name', 'page', 'clip', 'entry', 'alt', 'info'):
            if key not in m:
                _fail(code, f'every entry of "montages" needs a "{key}" field; got '
                            f'{m.get("name", m)!r}.')
        if not (isinstance(m['clip'], (list, tuple)) and len(m['clip']) == 4):
            _fail(code, f'montage {m["name"]!r}: "clip" must be [x0, y0, x1, y1] in PDF points. '
                        f'Run  python tools/inspect_pdf.py {code} --grid <page>  to read them off.')

    # --- inline symbols
    for ins in raw.get('inlineSymbols', []):
        for key in ('entry', 'after', 'icon'):
            if key not in ins:
                _fail(code, f'every entry of "inlineSymbols" needs a "{key}" field; got {ins!r}.')

    # --- icon art (extract_icons.py clips each symbol by page + rect)
    art = raw.get('iconArt', {})
    if not isinstance(art, dict):
        _fail(code, f'"iconArt" must be an object, got {art!r}.')
    for name, sm in art.get('symbols', {}).items():
        if not isinstance(sm, dict):
            _fail(code, f'iconArt symbol {name!r} must be an object with "page" and "rect".')
        for key in ('page', 'rect'):
            if key not in sm:
                _fail(code, f'iconArt symbol {name!r} needs a "{key}" field; got {sm!r}.')
        if not (isinstance(sm['rect'], (list, tuple)) and len(sm['rect']) == 4):
            _fail(code, f'iconArt symbol {name!r}: "rect" must be [x0, y0, x1, y1] in PDF '
                        f'points.\n  Read them off with:  python tools/inspect_pdf.py {code} '
                        f'--grid {sm.get("page", "<page>")}')

    # --- patterns must compile
    patterns = raw['patterns']
    for key in ('trigger', 'pageWord', 'pageRef'):
        if key not in patterns:
            _fail(code, f'"patterns.{key}" is required.')
        try:
            re.compile(patterns[key], re.I)
        except re.error as e:
            _fail(code, f'"patterns.{key}" is not a valid regular expression: {e}.\n'
                        f'  Remember JSON needs doubled backslashes: "\\\\s+" not "\\s+".')
    if not re.compile(patterns['pageRef'], re.I).groups:
        _fail(code, '"patterns.pageRef" must capture the page number in a group, '
                    'e.g. "auf Seite\\\\s*(\\\\d+)" — note the parentheses.')

    # --- ui.json
    for key in ('months', 'strings'):
        if key not in ui:
            raise PackError(f'langs/{code}/ui.json: missing required field "{key}".')
    if not isinstance(ui['months'], list) or len(ui['months']) != 12:
        raise PackError(f'langs/{code}/ui.json: "months" must be a list of exactly 12 names, '
                        f'January first.')
    # A group the pack files sections under but never names would reach the navigation as
    # a heading with no words in it. Checked here rather than left to the "en" fallback,
    # because falling back would print a group heading in English inside a Spanish menu
    # and nothing would look broken enough to notice.
    used = []
    for s in raw['sections']:
        if s.get('group') and s['group'] not in used:
            used.append(s['group'])
    unnamed = [g for g in used if not ui['strings'].get('grp' + g)]
    if unnamed:
        raise PackError(
            f'langs/{code}/ui.json: no name for the section group(s) '
            f'{", ".join(repr(g) for g in unnamed)}.\n'
            f'  langs/{code}/lang.json files sections under them, so the menu would print an '
            f'empty heading. Add {", ".join(repr("grp" + g) for g in unnamed)} to "strings".')


def load_all(only=None):
    """Every pack (or just `only`), validated. Raises on the first bad one —
    for callers that want all-or-nothing. Most callers want load_valid."""
    return [load(c) for c in resolve(only)]


def load_valid(only=None):
    """Load what loads: returns (packs, [(code, message)]).

    For everything that must keep working when one pack is broken — building the
    other languages, rendering the shared icons, starting a new pack.
    """
    packs, errors = [], []
    for c in resolve(only):
        try:
            packs.append(load(c))
        except PackError as e:
            errors.append((c, str(e)))
    return packs, errors


def icon_art_pack(packs=None):
    """The pack whose PDF carries the game-icon artwork. The glyphs are the same
    in every edition, so exactly one pack renders them for everybody."""
    if packs is None:
        packs, _errs = load_valid()
    provs = [p for p in packs if p.icon_art.get('provides')]
    if not provs:
        return None
    if len(provs) > 1:
        raise PackError(
            'more than one pack claims "iconArt.provides": '
            f'{", ".join(p.code for p in provs)}. The game icons are language-independent, '
            'so exactly one pack renders them. Set "provides": false in the others.')
    return provs[0]


# ---- registry --------------------------------------------------------------
def build_registry(packs=None):
    """The list the browser fetches to know which languages exist.

    A language is listed only once its grimoire JSON has actually been built, so
    a half-finished pack can sit in langs/ without putting a dead button in the
    header.
    """
    if packs is None:
        packs, _errs = load_valid()
    listed, skipped = [], []
    for p in packs:
        if not os.path.exists(p.data_path):
            skipped.append(p.code)
            continue
        entry = {
            'code': p.code,
            'name': p.name,
            'label': p.label,
            'dir': p.text_dir,
            'order': p.order,
            'ui': f'langs/{p.code}/ui.json',
            'data': f'data/grimoire_{p.code}.json',
            # The newest edition this language has. A translation lands months
            # after the English original, and the registry is the only thing the
            # browser reads before choosing a language — so it is the only place
            # a language can find out that another one is already ahead of it.
            'v': p.current['v'],
            'date': p.current['date'],
        }
        # A pack may ship a flag next to its config. It is decoration: the label
        # is what names the language, so a pack without one is perfectly fine.
        # Listed rather than os.path.exists()-ed: that check is case-insensitive
        # on Windows and macOS, so a "Flag.svg" would build green here and 404
        # on the Linux host that serves the site.
        if 'flag.svg' in os.listdir(p.dir):
            entry['flag'] = f'langs/{p.code}/flag.svg'
        elif any(f.lower() == 'flag.svg' for f in os.listdir(p.dir)):
            print(f'  [warn] langs/{p.code}: the flag must be named exactly "flag.svg" '
                  f'(all lowercase) — the web server is case-sensitive. Not using it.')
        listed.append(entry)
    listed.sort(key=lambda x: (x['order'], x['code']))
    if not any(x['code'] == DEFAULT_LANG for x in listed) and listed:
        raise PackError(
            f'the default language "{DEFAULT_LANG}" has no built grimoire '
            f'(data/grimoire_{DEFAULT_LANG}.json). Build it before the others, or change '
            f'DEFAULT_LANG in tools/langpack.py.')
    return {'default': DEFAULT_LANG, 'languages': listed}, skipped


def write_registry(packs=None, quiet=False):
    reg, skipped = build_registry(packs)
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, 'languages.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write('\n')
    if not quiet:
        print(f'  registry -> data/languages.json: '
              f'{", ".join(x["code"] for x in reg["languages"])}')
        for c in skipped:
            print(f'  [note] langs/{c}/ is not listed yet: data/grimoire_{c}.json has not '
                  f'been built. Run: python tools/ingest.py {c}')
    return reg


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        packs, errors = load_valid(sys.argv[1:] or None)
    except PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
    for p in packs:
        art = ' · renders the game icons' if p.icon_art.get('provides') else ''
        pdf = 'ok' if p.has_pdf() else 'MISSING'
        print(f'  OK    {p.code}  {p.name:<10} v{p.current["v"]:<5} '
              f'{len(p.sections)} sections · {len(p.montages)} montages · PDF {pdf}{art}')
    for code, msg in errors:
        print(f'  BAD   {code}\n{msg}\n', file=sys.stderr)
    print(f'\n{len(packs)} pack(s) valid, {len(errors)} broken.')
    sys.exit(1 if errors else 0)
