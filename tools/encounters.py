# -*- coding: utf-8 -*-
"""Build data/encounters_es.json and stage the themed chapter-1 encounter-set images.

The "Conjuntos de encuentros del capítulo 1" viewer (Resources section `faq-encounters`) shows
Rincón Miskatonic's full-art reskins of the Core Set (2016) encounter cards, one themed variant per
campaign. This is the committed, reproducible builder for its DATA + ASSETS. Spanish only for now.

Run it WITHOUT -I (Pillow lives in the user site-packages, which -I hides):
    python tools/encounters.py            # rebuild data + stage every campaign (no-bleed + bleed + icons)
    python tools/encounters.py --data     # only rebuild data/encounters_es.json

=========================  HOW TO ADD A NEW CAMPAIGN  =========================
1. In the Google Drive source folder (SRC below), the campaign lives as "NN - <Name>" with one
   "MM - <Set>" folder per encounter set, each holding `Exportad*` (no-bleed) + `Exportad* 3mm
   sangrado` (bleed) + Icon.png. WAIT for Google Drive to finish syncing — freshly-touched files
   lag, and a half-synced folder stages short (verify staged == 2*physical, which this does).
2. Read the campaign's Guía pages (`N_PDFsam_Guia...pdf` in its folder) for which Core sets it
   uses and any "only gather the X cards" notes. The folders present ARE the sets it reuses; their
   composition (names/copies/order) is SHARED per setcode (from ArkhamDB), so you just list the codes.
3. If a folder is a SUBSET of a set (e.g. Carcosa's Midnight Masks = only the 5 treacheries), make a
   NEW setcode (like `the_midnight_masks_tr`), give it its own entry in SCEN_COMP, and add a
   FOLDER_OVERRIDE so staging maps that campaign's folder number to the new code. Copy its icon
   (same symbol) in stage().
4. Add CAMP_SRC[<id>] = "NN - <Name>" and, in CAMPAIGNS, change the campaign from {'pending': True}
   to {'sets': [<codes in folder order>]}.
5. `python tools/encounters.py`  →  then `python tools/build_pwa_manifests.py`  →  then §7 ship.
   Card names auto-link to ArkhamDB via `cnum` (code = '01' + cnum), so keep cnum right.
==============================================================================
"""
import io, os, json, glob, sys, pathlib
from collections import defaultdict
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Fernando's local themed-art folder (Google Drive). Machine-specific — edit if it moves.
SRC = pathlib.Path(r'C:/Users/Fernando/Mi unidad/Rincon Miskatonic/Contenido AH LCG/Encuentros del core 1 tematizados')
OUT = ROOT / 'assets' / 'encounters'

# Spanish display name per setcode.
SETNAME = {
    'agents_of_cthulhu': 'Agentes de Cthulhu', 'agents_of_hastur': 'Agentes de Hastur',
    'agents_of_shub': 'Agentes de Shub-Niggurath', 'agents_of_yog': 'Agentes de Yog-Sothoth',
    'ancient_evils': 'Antiguos males', 'chilling_cold': 'Frío helador', 'pentagram': 'Secta oscura',
    'ghouls': 'Gules', 'rats': 'Ratas', 'locked_doors': 'Puertas cerradas',
    'striking_fear': 'Miedo impactante', 'nightgaunts': 'Ángeles descarnados',
    'the_midnight_masks': 'Las Máscaras de Medianoche',
    'the_devourer_below': 'El Devorador de las Profundidades',
    'the_midnight_masks_tr': 'Las Máscaras de Medianoche',   # Carcosa: only the 5 treacheries
}
# Source folder NUMBER -> setcode (consistent across campaigns; the base box defines the numbering).
NUM2CODE = {'01': 'agents_of_cthulhu', '02': 'agents_of_hastur', '03': 'agents_of_shub',
            '04': 'agents_of_yog', '05': 'ancient_evils', '06': 'chilling_cold', '07': 'pentagram',
            '08': 'ghouls', '09': 'rats', '10': 'locked_doors', '11': 'striking_fear',
            '12': 'nightgaunts', '13': 'the_midnight_masks', '14': 'the_devourer_below'}
# (campaignId, folder number) -> setcode, when a campaign's folder is NOT the base-box set.
FOLDER_OVERRIDE = {('the-path-to-carcosa', '13'): 'the_midnight_masks_tr'}

BASE_SETS = ['agents_of_cthulhu', 'agents_of_hastur', 'agents_of_shub', 'agents_of_yog',
             'ancient_evils', 'chilling_cold', 'pentagram', 'ghouls', 'rats', 'locked_doors',
             'striking_fear', 'nightgaunts', 'the_midnight_masks', 'the_devourer_below']
DUNWICH_SETS = ['agents_of_yog', 'ancient_evils', 'chilling_cold', 'pentagram', 'rats',
                'locked_doors', 'striking_fear', 'nightgaunts']
CARCOSA_SETS = ['agents_of_hastur', 'ancient_evils', 'chilling_cold', 'pentagram', 'ghouls',
                'rats', 'locked_doors', 'striking_fear', 'the_midnight_masks_tr']

# Curated sets that don't map 1:1 to one ArkhamDB code. Decoded from the official PnP PDFs
# (00 - Original/Ingles, page order == themed image order). Locations are 1 copy, two real faces
# (odd=unrevealed, even=revealed); treacheries are odd front / shared even back, N copies.
# enum = encounter-set number (ArkhamDB encounter_position); cnum = collection number (position).
SCEN_COMP = {
    'the_midnight_masks': {'name': SETNAME['the_midnight_masks'], 'cards': [
        {'name': 'Barrio Fluvial', 'type': 'location', 'copies': 1, 'enum': 6, 'cnum': 125},
        {'name': 'Barrio Sur', 'subtitle': 'Sociedad Histórica', 'type': 'location', 'copies': 1, 'enum': 7, 'cnum': 126},
        {'name': 'Barrio Sur', 'subtitle': 'Pensión de Ma', 'type': 'location', 'copies': 1, 'enum': 8, 'cnum': 127},
        {'name': 'Hospital de Santa María', 'type': 'location', 'copies': 1, 'enum': 9, 'cnum': 128},
        {'name': 'Universidad Miskatonic', 'type': 'location', 'copies': 1, 'enum': 10, 'cnum': 129},
        {'name': 'Centro', 'subtitle': 'Primer Banco de Arkham', 'type': 'location', 'copies': 1, 'enum': 11, 'cnum': 130},
        {'name': 'Centro', 'subtitle': 'Manicomio Arkham', 'type': 'location', 'copies': 1, 'enum': 12, 'cnum': 131},
        {'name': 'Barrio Este', 'type': 'location', 'copies': 1, 'enum': 13, 'cnum': 132},
        {'name': 'Barrio Norte', 'type': 'location', 'copies': 1, 'enum': 15, 'cnum': 134},
        {'name': 'Sombra acechante', 'type': 'treachery', 'copies': 3, 'enum': 16, 'cnum': 135},
        {'name': 'Pista falsa', 'type': 'treachery', 'copies': 2, 'enum': 19, 'cnum': 136},
    ]},
    'the_devourer_below': {'name': SETNAME['the_devourer_below'], 'cards': [
        {'name': 'Bosques de Arkham', 'subtitle': sub, 'type': 'location', 'copies': 1, 'enum': ep, 'cnum': cn}
        for sub, ep, cn in (('Terreno impío', 9, 150), ('Senderos sinuosos', 10, 151), ('Casa vieja', 11, 152),
                            ('Pared del acantilado', 12, 153), ('Espesura enmarañada', 13, 154), ('Claro tranquilo', 14, 155))
    ]},
    'the_midnight_masks_tr': {'name': SETNAME['the_midnight_masks_tr'], 'cards': [
        {'name': 'Sombra acechante', 'type': 'treachery', 'copies': 3, 'enum': 16, 'cnum': 135},
        {'name': 'Pista falsa', 'type': 'treachery', 'copies': 2, 'enum': 19, 'cnum': 136},
    ]},
}
# Built campaigns -> their Google Drive source folder. Pending campaigns are not here.
CAMP_SRC = {'night-of-the-zealot': '01 - La Noche de la Fanática',
            'the-dunwich-legacy': '02 - El Legado de Dunwich',
            'the-path-to-carcosa': '03 - El Camino a Carcosa'}
CAMPAIGNS = [
    {'id': 'night-of-the-zealot', 'name': 'La Noche de la Fanática', 'default': True, 'sets': BASE_SETS},
    {'id': 'the-dunwich-legacy', 'name': 'El Legado de Dunwich', 'sets': DUNWICH_SETS},
    {'id': 'the-path-to-carcosa', 'name': 'El Camino a Carcosa', 'sets': CARCOSA_SETS},
    {'id': 'the-forgotten-age', 'name': 'La Era Olvidada', 'pending': True},
    {'id': 'the-circle-undone', 'name': 'El Círculo Roto', 'pending': True},
    {'id': 'the-dream-eaters', 'name': 'Los Devoradores de Sueños', 'pending': True},
    {'id': 'the-innsmouth-conspiracy', 'name': 'La Conspiración de Insmouth', 'pending': True},
    {'id': 'edge-of-the-earth', 'name': 'Los Confines de la Tierra', 'pending': True},
    {'id': 'the-scarlet-keys', 'name': 'Las Llaves Escarlata', 'pending': True},
    {'id': 'the-feast-of-hemlock-vale', 'name': 'La Fiesta del Valle de la Cicuta', 'pending': True},
    {'id': 'the-drowned-city', 'name': 'La Ciudad Sumergida', 'pending': True},
]

def code_for(camp_id, num):
    return FOLDER_OVERRIDE.get((camp_id, num)) or NUM2CODE.get(num)

# ---------- data ----------
def _adb_by_code():
    cards = json.load(open(ROOT / 'tools/other/_adb/cards_es.json', encoding='utf-8'))
    by = defaultdict(list)
    for c in cards:
        if isinstance(c, dict) and c.get('pack_code') == 'core' and c.get('encounter_code'):
            by[c['encounter_code']].append(c)
    return by

def build_data():
    by = _adb_by_code()
    def compose(code):
        if code in SCEN_COMP:
            return SCEN_COMP[code]
        cs = sorted(by[code], key=lambda c: c.get('encounter_position') or 0)
        return {'name': SETNAME[code],
                'cards': [{'name': c['name'], 'type': c.get('type_code'), 'copies': c.get('quantity') or 1,
                           'enum': c.get('encounter_position'), 'cnum': c.get('position')} for c in cs]}
    codes = set(BASE_SETS)
    for camp in CAMPAIGNS:
        codes.update(camp.get('sets', []))
    sets = {code: compose(code) for code in sorted(codes)}
    data = {'campaigns': CAMPAIGNS, 'sets': sets}
    out = ROOT / 'data/encounters_es.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    pend = sum(1 for c in CAMPAIGNS if c.get('pending'))
    print(f'  data: {len(CAMPAIGNS)} campaigns ({pend} pending), {len(sets)} sets -> {out.name}')

# ---------- assets ----------
def _nobleed(setdir):
    for d in glob.glob(os.path.join(setdir, 'Exportad*')):
        if os.path.isdir(d) and 'sangr' not in os.path.basename(d).lower():
            return d

def _bleed(setdir):
    for d in glob.glob(os.path.join(setdir, 'Exportad* 3mm sangrado')):
        if os.path.isdir(d):
            return d

def _webp(png):
    buf = io.BytesIO(); Image.open(png).convert('RGBA').save(buf, 'WEBP', quality=85, method=6)
    return buf.getvalue()

def stage():
    # composition is needed to verify staged == 2*physical and which icons to copy
    data = json.load(open(ROOT / 'data/encounters_es.json', encoding='utf-8'))
    phys_of = {code: sum(cc['copies'] for cc in s['cards']) for code, s in data['sets'].items()}
    stats = {'written': 0, 'same': 0}
    icon_written = 0
    for camp_id, folder in CAMP_SRC.items():
        for setdir in sorted(glob.glob(os.path.join(SRC, folder, '[0-9][0-9] *'))):
            code = code_for(camp_id, os.path.basename(setdir)[:2])
            if not code:
                continue
            for src_dir, suffix in ((_nobleed(setdir), ''), (_bleed(setdir), '-bleed')):
                if not src_dir:
                    continue
                for png in sorted(glob.glob(os.path.join(src_dir, '*.png'))):
                    num = os.path.basename(png).split('.')[0]
                    if not num.isdigit():
                        continue
                    dest = OUT / camp_id / (code + suffix) / (num + '.webp')
                    d = _webp(png)
                    if dest.exists() and dest.read_bytes() == d:
                        stats['same'] += 1
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(d); stats['written'] += 1
            # icon: from the base-box set (or this folder) -> assets/encounters/icons/<code>.webp
            ic = OUT / 'icons' / (code + '.webp')
            if not ic.exists():
                src_icon = os.path.join(setdir, 'Icon.png')
                if os.path.exists(src_icon):
                    ic.parent.mkdir(parents=True, exist_ok=True)
                    buf = io.BytesIO(); Image.open(src_icon).convert('RGBA').save(buf, 'WEBP', quality=90, method=6)
                    ic.write_bytes(buf.getvalue()); icon_written += 1
    print(f"  assets: {stats['written']} webp written, {stats['same']} unchanged, {icon_written} icons")
    # completeness: every built set has 2*physical no-bleed AND 2*physical bleed images
    bad = 0
    for camp in data['campaigns']:
        if camp.get('pending'):
            continue
        for code in camp['sets']:
            want = 2 * phys_of[code]
            for suffix in ('', '-bleed'):
                got = len(glob.glob(str(OUT / camp['id'] / (code + suffix) / '*.webp')))
                if got != want:
                    print(f"  !! {camp['id']}/{code}{suffix}: {got}/{want}"); bad += 1
    print('  completeness: OK' if not bad else f'  completeness: {bad} MISMATCHES (check Google Drive sync)')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build_data()
    if '--data' not in sys.argv:
        stage()

if __name__ == '__main__':
    main()
