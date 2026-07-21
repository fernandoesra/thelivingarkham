# -*- coding: utf-8 -*-
"""Start a new language pack.

    python tools/new_lang.py de

Creates langs/de/ with a lang.json skeleton to fill in, a ui.json seeded with
the English strings to translate, and an empty source/ folder for the PDFs.
Nothing else in the project needs touching.
"""
import json, os, shutil, sys
import langpack

SEED_UI = 'en'          # ui.json starts as this language's strings, ready to translate


def create(code):
    if not code or not code.isalpha() or not (2 <= len(code) <= 5):
        raise langpack.PackError(
            f'"{code}" is not a language code. Use the short ISO code, e.g. de, fr, it, pt.')
    code = code.lower()
    dest = os.path.join(langpack.LANGS_DIR, code)
    if os.path.exists(dest):
        raise langpack.PackError(
            f'langs/{code}/ already exists. Edit it, or delete it first if you want to start over.')

    os.makedirs(os.path.join(dest, 'source'), exist_ok=True)

    # lang.json: a skeleton of TODOs. Deliberately not pre-filled with plausible
    # content — a pack that looks finished but is wrong is worse than an obvious blank.
    tpl = os.path.join(langpack.LANGS_DIR, '_template', 'lang.json')
    raw = json.load(open(tpl, encoding='utf-8'))
    raw['code'] = code
    raw['label'] = code.upper()
    # last in the switcher by default. Read cheaply: a broken pack elsewhere
    # must not stop you starting a new one.
    raw['order'] = max([langpack._declared_order(c) for c in langpack.codes()] or [0]) + 1
    _write(os.path.join(dest, 'lang.json'), raw)

    # ui.json: a copy of the fallback language's, so the key set can never drift —
    # copied wholesale rather than field by field, or a key added to ui.json later
    # would silently stop reaching new packs. English text left in place means
    # "not translated yet", which is exactly what it means.
    ui = json.loads(json.dumps(langpack.load(SEED_UI).ui))   # deep copy
    ui['code'] = code
    ui['fallback'] = SEED_UI
    ui['locale'] = code
    _write(os.path.join(dest, 'ui.json'), ui)

    print(f"""Created langs/{code}/

  langs/{code}/source/     <- put your Grimoire PDF(s) here
  langs/{code}/lang.json   <- describes your PDF (fill in every TODO)
  langs/{code}/ui.json     <- the interface, seeded in English: translate the values
  langs/{code}/flag.svg    <- optional: add one and the switcher shows it

Next:
  1. Copy the PDF into langs/{code}/source/ and write its filename into
     lang.json under "book" -> "versions" -> "pdf".
  2. See what chapters your PDF has, and get a "sections" block to paste:
       python tools/inspect_pdf.py {code} --sections
  3. Build it:
       python tools/ingest.py {code}
  4. Look at it:
       npm run dev      then open  http://localhost:8080/#{code}/

The full walkthrough is in README.md -> "Adding a language".""")
    return dest


def _write(path, obj):
    # newline='': every other JSON in this repo is LF-terminated, and Python's text mode on
    # Windows would write CRLF — which turns the next one-line edit of the file into a diff
    # that replaces every line of it.
    with open(path, 'w', encoding='utf-8', newline='') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def create_ui_only(code, name, label, order=None):
    """Start a pack that translates the INTERFACE and has no rulebook.

    The Grimoire and the FAQ exist in four languages; ArkhamDB serves eleven. A reader in one
    of the other seven still gets the landing, the tutorial, the footer and the release notes in
    their own words, and is told in their own words that the books are not available yet — which
    is a far better answer than a site they cannot read at all. No source/ folder is made: there
    is no PDF to put in it, and an empty one only invites the question."""
    code = (code or '').lower()
    dest = os.path.join(langpack.LANGS_DIR, code)
    if os.path.exists(dest):
        raise langpack.PackError(f'langs/{code}/ already exists.')
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, 'lang.json'), {
        'code': code, 'name': name, 'label': label, 'dir': 'ltr',
        'order': order if order is not None
        else max([langpack._declared_order(c) for c in langpack.codes()] or [0]) + 1,
        'uiOnly': True,
    })
    ui = json.loads(json.dumps(langpack.load(SEED_UI).ui))   # deep copy
    ui['code'] = code
    ui['fallback'] = SEED_UI
    ui['locale'] = code
    _write(os.path.join(dest, 'ui.json'), ui)
    print(f'Created langs/{code}/ (interface only) — translate the values in ui.json.')
    return dest


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python tools/new_lang.py <code>      e.g. de\n'
              '       python tools/new_lang.py <code> --ui-only "<name>" <LABEL>',
              file=sys.stderr)
        return 2
    if '--ui-only' in sys.argv:
        rest = [a for a in sys.argv[2:] if a != '--ui-only']
        if len(rest) < 2:
            print('usage: python tools/new_lang.py <code> --ui-only "<name>" <LABEL>',
                  file=sys.stderr)
            return 2
        create_ui_only(sys.argv[1], rest[0], rest[1])
        return 0
    create(sys.argv[1])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except langpack.PackError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
