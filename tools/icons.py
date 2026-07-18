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


def is_icon_font(font):
    return 'ArkhamHorror' in font


def icon_names(packs=()):
    """Every icon a pack may label: the font glyphs plus any vector symbols a
    pack renders (e.g. the basic-weakness symbol, which is drawn, not typed)."""
    names = set(ICON_MAP.values())
    for p in packs:
        names |= set(p.icon_art.get('symbols', {}))
    return sorted(names)
