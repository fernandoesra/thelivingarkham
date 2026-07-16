# -*- coding: utf-8 -*-
"""Extra visual resources embedded in glossary entries.

Three kinds, all driven from this single config (shared by parse_grimoire.py,
render_images.py, extract_icons.py and assemble.py):

  MONTAGES       — example card-art / diagram regions rendered to flat images and
                   attached to their entry; their overlaid text is masked out of the
                   body and offered as a textual alternative (an "i" info panel).
  SYMBOL_MASKS   — standalone symbols drawn as vectors in the PDF (e.g. the basic
                   weakness symbol) rendered to a recolourable alpha-mask icon.
  INLINE_SYMBOLS — where to re-insert those symbols into the parsed body (they are
                   graphics, so the text parser never sees them).

Coordinates are PDF points for the specific source PDF (see PDF_LANG).
`page` is the PDF page (for rendering/masking); `srcpage` is the printed book page
(for the "Grimoire figure · p. N" credit — differs from `page` on the EN spread PDF).
"""

PDF_LANG = {
    'AHLCG_Grimorio_v_1_0_Capitulo2.pdf': 'es',
    'arkham_grimoire_v11.pdf': 'en',
    'arkham_grimoire_v_1_0.pdf': 'en',
}

MONTAGES = {
 'es': [
   {'name': 'montage-move', 'page': 20, 'srcpage': 20, 'clip': (330, 57, 584, 183), 'entry': 'Moverse',
    'alt': 'Dos cartas de Lugar (Distrito comercial y Distrito ribereño) unidas por una flecha, ilustrando el movimiento entre Lugares conectados.',
    'info': '<p><b>Distrito comercial</b> — Lugar · Arkham (Central). '
            '<i>Durante tu turno, si hay exactamente 1 o 2 investigadores en la partida: '
            'Muévete a un Lugar conectado. Límite de una vez por ronda.</i></p>'
            '<p><b>Distrito ribereño</b> — Lugar · Arkham. '
            '<i>Con sus calles perpetuamente inundadas, el antiguo Barrio Fluvial es una ciudad fantasma…</i></p>'},
   {'name': 'montage-victory', 'page': 27, 'srcpage': 27, 'clip': (70, 522, 262, 688), 'entry': 'Victoria X',
    'alt': 'Dos cartas que valen puntos de victoria: el Enemigo Naomi O’Bannion y el Lugar Biblioteca Orne.',
    'info': '<p><b>Naomi O’Bannion</b> — Enemigo · Humanoide, Sindicato, Élite. Represalia. '
            'Gasta 1 recurso: Negociar. <b>Victoria 1.</b></p>'
            '<p><b>Biblioteca Orne</b> — Lugar · Miskatonic. '
            '«Roba 3 cartas. Límite de una vez por partida.» <b>Victoria 1.</b></p>'},
   {'name': 'montage-slots', 'page': 14, 'srcpage': 14, 'clip': (338, 28, 585, 175), 'entry': 'Espacios',
    'alt': 'Los ocho tipos de espacio con su icono: accesorio, cabeza, cuerpo, aliado, mano (1 y 2 espacios) y arcano (1 y 2 espacios).',
    'info': '<p>Tipos de espacio y su símbolo: <b>accesorio</b>, <b>cabeza</b>, <b>cuerpo</b> y '
            '<b>aliado</b> (1 espacio de cada uno); <b>mano</b> y <b>arcano</b> (1 o 2 espacios).</p>'},
 ],
 'en': [
   {'name': 'montage-move', 'page': 9, 'srcpage': 17, 'clip': (658, 156, 898, 281), 'entry': 'Move',
    'alt': 'Two location cards (Merchant District and Waterfront District) joined by an arrow, illustrating movement between connecting locations.',
    'info': '<p><b>Merchant District</b> — Location · Arkham (Central). '
            '<i>During your turn, if there are exactly 1 or 2 investigators in the game: '
            'Move to a connecting location. (Limit once per round.)</i></p>'
            '<p><b>Waterfront District</b> — Location · Arkham. '
            '<i>With its streets perpetually flooded, the former Rivertown district is a ghost town…</i></p>'},
   {'name': 'montage-victory', 'page': 13, 'srcpage': 24, 'clip': (345, 327, 535, 486), 'entry': 'Victory X',
    'alt': 'Two cards worth victory points: the enemy Naomi O’Bannion and the location Orne Library.',
    'info': '<p><b>Naomi O’Bannion</b> — Enemy · Humanoid, Syndicate, Elite. Retaliate. '
            'Spend 1 resource: Parley. <b>Victory 1.</b></p>'
            '<p><b>Orne Library</b> — Location · Miskatonic. '
            '“Draw 3 cards. (Limit once per game.)” <b>Victory 1.</b></p>'},
   {'name': 'montage-slots', 'page': 11, 'srcpage': 21, 'clip': (948, 286, 1156, 438), 'entry': 'Slots',
    'alt': 'The eight slot types with their icon: accessory, head, body, ally, hand (1 and 2 slots) and arcane (1 and 2 slots).',
    'info': '<p>Slot types and their symbol: <b>accessory</b>, <b>head</b>, <b>body</b> and '
            '<b>ally</b> (1 slot each); <b>hand</b> and <b>arcane</b> (1 or 2 slots).</p>'},
 ],
}

# Standalone symbols drawn as PDF vectors -> recolourable alpha-mask icons.
# Rendered by extract_icons.py from the ES PDF (language-independent artwork).
SYMBOL_MASKS = {
    'weakness': {'pdf': 'AHLCG_Grimorio_v_1_0_Capitulo2.pdf', 'page': 11, 'rect': (144, 164, 190, 210),
                 'es': 'Símbolo de Debilidad básica', 'en': 'Basic weakness symbol'},
}

# Re-insert a symbol icon as a centred block right after the body block whose text
# ends with `after` (the parser never sees these graphics).
INLINE_SYMBOLS = {
 'es': [
   {'entry': 'Debilidad',     'after': 'el siguiente símbolo:', 'icon': 'weakness'},
   {'entry': 'Robar cartas',  'after': 'completa el robo.',     'icon': 'weakness'},
 ],
 'en': [
   {'entry': 'Weakness',      'after': 'the following symbol:', 'icon': 'weakness'},
 ],
}


def masks_for(pdf_basename):
    """Return {page(1-idx): [(x0,y0,x1,y1), ...]} of montage regions in this PDF,
    used to drop the overlaid card/label text from the parsed body."""
    lang = PDF_LANG.get(pdf_basename)
    res = {}
    for m in MONTAGES.get(lang, []):
        res.setdefault(m['page'], []).append(m['clip'])
    return res
