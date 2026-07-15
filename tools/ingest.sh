#!/usr/bin/env bash
# ------------------------------------------------------------------
# Content pipeline: source PDFs  ->  data/*.json  +  assets/{icons,img}
# Run when a new Grimoire version is published.  Requires Python with
# pymupdf, Pillow, numpy  (see requirements.txt).
#   $ bash tools/ingest.sh        (or: npm run ingest)
# ------------------------------------------------------------------
set -e
export PYTHONIOENCODING=utf-8
HERE="$(cd "$(dirname "$0")" && pwd)"      # tools/
ROOT="$(cd "$HERE/.." && pwd)"             # project root
cd "$ROOT"

SRC=tools/source
DATA=data
IMG=assets/img
ICONS=assets/icons
ES="$SRC/AHLCG_Grimorio_v_1_0_Capitulo2.pdf"
EN="$SRC/arkham_grimoire_v11.pdf"
mkdir -p "$DATA" "$IMG" "$ICONS"

echo "== parse PDFs =="
python tools/parse_grimoire.py "$ES" "$DATA/_nodes_es.json"
python tools/parse_grimoire.py "$EN" "$DATA/_nodes_en.json"

echo "== render figures =="
python tools/render_images.py "$SRC" "$IMG" 2.2 88

echo "== extract game icons =="
python tools/extract_icons.py "$ES" "$ICONS"

echo "== assemble grimoire JSON =="
python tools/assemble.py es "$DATA/_nodes_es.json" "$IMG/images.json" "$DATA/grimoire_es.json"
python tools/assemble.py en "$DATA/_nodes_en.json" "$IMG/images.json" "$DATA/grimoire_en.json"

echo "== coverage check =="
python tools/validate_coverage.py es "$DATA/grimoire_es.json" "$ES" | head -1
python tools/validate_coverage.py en "$DATA/grimoire_en.json" "$EN" | head -1

echo "== done -> data/ and assets/ updated. Preview with: npm run dev =="
