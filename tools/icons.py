# -*- coding: utf-8 -*-
"""The game's icon glyphs — the one place their identity is defined.

The Arkham icon font maps private-use codepoints to game symbols. That mapping
is a property of the font, not of any language, so it lives here and is shared
by the parser (which turns glyphs into `icon` runs) and the icon renderer (which
turns them into recolourable PNG masks).

Human-readable labels are NOT here: they are per-language and live in each
pack's ui.json under "icons".
"""

# PUA codepoint -> semantic name (derived from the icon-reference page)
ICON_MAP = {
    0xF250: 'willpower', 0xF251: 'agility', 0xF252: 'intellect', 0xF253: 'combat', 0xF26C: 'wild',
    0xF254: 'rogue', 0xF255: 'survivor', 0xF256: 'guardian', 0xF257: 'mystic', 0xF258: 'seeker',
    0xF259: 'action', 0xF25A: 'free', 0xF26D: 'reaction',
    0xF25B: 'skull', 0xF25C: 'cultist', 0xF25D: 'autofail', 0xF25E: 'elderthing',
    0xF25F: 'eldersign', 0xF260: 'tablet', 0xF261: 'unique', 0xF263: 'perinvestigator',
    0xF278: 'codex',
    # The two newer chaos tokens. The Grimoire's own PDF never prints them, so their
    # glyphs are traced from the FAQ font instead (see extract_icons.fill_from_faq).
    0xF26E: 'bless', 0xF26F: 'curse',
}

# A second cut of the same face. The German and Italian books embed TWO icon fonts —
# ArkhamHorrorLCGU (the codepoints above) and ArkhamHorrorLCG, which draws the same
# icon set at a block of private-use codepoints this far along. In the Italian FAQ the
# second font carries most of the icons (188 of 241), so without this they would parse
# as "unknown".
#
# The offset is measured, not assumed. Eleven of the 21 codepoints those books use also
# appear in the first font *inside the same document*, and each pair's glyph outlines
# are identical point for point (the German and Italian PDFs embed a newer cut than the
# Spanish and English ones, so outlines only compare within a document). The remaining
# ten are named by the books' own prose, which prints each symbol beside its word —
# "Willenskraft (<willpower>), Intellekt (<intellect>), Kampf (<combat>)" on page 38 of
# the German book — and lists the four chaos tokens in the same order as every other
# edition. Twenty-one codepoints, no contradictions.
ALT_OFFSET = 0xE2F20

# Two glyphs the German FAQ addresses at plain ASCII codepoints instead of the private-use
# area. They are only ever reached through an icon-font span, so they cannot collide with a
# typed "!" or "%": the rest of the alphabet is not in this font.
#
# Identified from the books themselves. The German question reads "Haben <21>- und <25>-Marker
# Modifikatoren oder Werte, falls sie außerhalb einer Fertigkeitsprobe enthüllt werden?" and
# the English edition asks the very same one: "Do <bless> and <curse> tokens have a modifier or
# value if they are revealed outside of a skill test?" — same question, same order, and the
# pair appears in that order in all eleven places the German document prints it.
ASCII_ICONS = {0x21: 'bless', 0x25: 'curse'}


def icon_name(cp):
    """-> the icon a codepoint means, from either font cut. None if it is neither."""
    return ICON_MAP.get(cp) or ICON_MAP.get(cp - ALT_OFFSET) or ASCII_ICONS.get(cp)


def is_icon_font(font):
    return 'ArkhamHorror' in font


def is_alien_font(font):
    """The Drowned City's alien script.

    Unlike the icon font, its characters are LETTERS: the book types an ordinary word and the
    face draws it in the alien alphabet, so the text layer holds "poder" while the page shows
    six glyphs. That makes it the opposite of an icon — the meaning is in the letters, and only
    the shape is alien — so it is kept as text and merely marked, and the site draws it with the
    same face. Reading it out as "p o d e r" is exactly right: the glyphs spell that."""
    return 'AlienGlyphs' in font


def icon_names(packs=()):
    """Every icon a pack may label: the font glyphs plus any vector symbols a
    pack renders (e.g. the basic-weakness symbol, which is drawn, not typed)."""
    names = set(ICON_MAP.values())
    for p in packs:
        names |= set(p.icon_art.get('symbols', {}))
    return sorted(names)
