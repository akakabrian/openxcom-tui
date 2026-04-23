"""Tile → (glyph, style) tables for geoscape and battlescape."""

from __future__ import annotations

from rich.style import Style


# Brightness budget from SKILL.md: terrain dim, infrastructure medium,
# units bright, cursor + alert brightest. All styles pre-parsed once.


# ---- geoscape ------------------------------------------------------------

# Two-glyph patterns keyed on (x+y) & 1 so land/ocean read as a painted
# canvas rather than `###########`.
GEO_OCEAN = ("≈", "~")
GEO_LAND  = (".", "·")
GEO_COAST = ("~", ",")

STYLE_OCEAN = Style(color="rgb(30,70,120)", bgcolor="rgb(8,12,25)")
STYLE_LAND  = Style(color="rgb(70,140,80)", bgcolor="rgb(10,22,14)")
STYLE_COAST = Style(color="rgb(100,140,150)", bgcolor="rgb(10,18,22)")

# Markers.
STYLE_BASE    = Style(color="rgb(255,220,80)", bgcolor="rgb(40,30,10)", bold=True)
STYLE_CITY    = Style(color="rgb(200,200,210)", bgcolor="rgb(15,15,20)", bold=False)
STYLE_UFO     = Style(color="rgb(240,80,80)",  bgcolor="rgb(25,10,10)", bold=True)
STYLE_CRAFT   = Style(color="rgb(120,220,240)", bgcolor="rgb(10,25,30)", bold=True)
STYLE_RADAR   = Style(color="rgb(50,90,140)",  bgcolor="rgb(12,20,35)")
STYLE_CURSOR  = Style(color="rgb(255,255,255)", bgcolor="rgb(80,60,10)", bold=True, reverse=True)


def geo_cell_style(kind: str) -> Style:
    return {
        "ocean": STYLE_OCEAN,
        "land":  STYLE_LAND,
        "coast": STYLE_COAST,
    }.get(kind, STYLE_OCEAN)


def geo_cell_glyph(kind: str, x: int, y: int) -> str:
    pair = {
        "ocean": GEO_OCEAN, "land": GEO_LAND, "coast": GEO_COAST,
    }.get(kind, GEO_OCEAN)
    return pair[(x + y) & 1]


# ---- battlescape ---------------------------------------------------------

BATTLE_PATTERN: dict[str, tuple[str, str]] = {
    "grass":       ("·", "."),
    "dirt":        (",", "."),
    "floor":       ("·", " "),
    "wall":        ("█", "█"),
    "tree":        ("♣", "^"),
    "door_closed": ("▢", "▢"),
    "door_open":   ("▫", "▫"),
    "water":       ("≈", "~"),
    "rubble":      ("▩", "░"),
}

BATTLE_STYLES: dict[str, Style] = {
    "grass":       Style(color="rgb(70,140,80)",  bgcolor="rgb(12,22,14)"),
    "dirt":        Style(color="rgb(160,130,90)", bgcolor="rgb(30,22,14)"),
    "floor":       Style(color="rgb(150,140,120)", bgcolor="rgb(20,20,18)"),
    "wall":        Style(color="rgb(180,170,150)", bgcolor="rgb(35,33,28)"),
    "tree":        Style(color="rgb(70,160,80)",  bgcolor="rgb(10,25,10)"),
    "door_closed": Style(color="rgb(210,180,120)", bgcolor="rgb(35,25,10)", bold=True),
    "door_open":   Style(color="rgb(210,180,120)", bgcolor="rgb(20,15,8)"),
    "water":       Style(color="rgb(60,120,200)", bgcolor="rgb(8,15,30)"),
    "rubble":      Style(color="rgb(150,140,130)", bgcolor="rgb(25,22,20)"),
}

UNIT_STYLE_PLAYER = Style(color="rgb(120,220,255)", bgcolor="rgb(10,20,30)", bold=True)
UNIT_STYLE_ALIEN  = Style(color="rgb(255,90,90)", bgcolor="rgb(30,10,10)", bold=True)
UNIT_STYLE_SELECTED = Style(color="rgb(255,255,120)", bgcolor="rgb(60,50,10)", bold=True, reverse=True)
UNIT_STYLE_DEAD = Style(color="rgb(110,90,90)", bgcolor="rgb(15,10,10)", italic=True)

CURSOR_STYLE = Style(color="rgb(255,255,255)", bgcolor="rgb(100,80,20)", reverse=True, bold=True)


UNKNOWN_STYLE = Style(color="rgb(255,80,220)", bgcolor="rgb(10,5,10)", bold=True)


def battle_tile_style(klass: str) -> Style:
    return BATTLE_STYLES.get(klass, UNKNOWN_STYLE)


def battle_tile_glyph(klass: str, x: int, y: int) -> str:
    pair = BATTLE_PATTERN.get(klass)
    if pair is None:
        return "?"
    return pair[(x + y) & 1]
