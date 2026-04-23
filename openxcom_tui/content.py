"""Game data — research projects, items, craft, UFOs, aliens, facilities.

All entries are hand-seeded from the original UFO: Enemy Unknown ruleset
(OpenXcom's ``bin/standard/xcom1/`` YAML). We keep names + costs
faithful to the source, strip sprites/sounds/map references, and
collapse heavy-asset entries (UFOpaedia text, animation tables) to a
single summary line so the TUI stays navigable without the vendor
tree.

If the vendored OXC repo is present under ``engine/openxcom``, the
optional ``augment_from_vendor()`` helper will merge any extra
research entries in the YAML that aren't in our hand-seeded list.
That makes this file the *canonical* source of truth — the vendor
data only adds, never overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# ---- research -----------------------------------------------------------

@dataclass(frozen=True)
class Research:
    id: str
    name: str
    cost: int                      # scientist-days to complete
    prerequisites: tuple[str, ...] = ()
    unlocks: tuple[str, ...] = ()  # research IDs unlocked on completion
    grants_item: Optional[str] = None  # manufacturable item id, if any


# Hand-seeded subset of the canonical UFO tech tree. Names + approximate
# costs mirror ``bin/standard/xcom1/research.rul``. We intentionally skip
# mid-game bloat like the full alien autopsy chain so the MVP reads
# clearly; augment_from_vendor() tops it up if the user ran bootstrap.
RESEARCH: dict[str, Research] = {
    r.id: r for r in [
        # Tier 0 — starting tech
        Research("STR_LASER_WEAPONS", "Laser Weapons", 80,
                 unlocks=("STR_LASER_PISTOL", "STR_LASER_RIFLE",
                          "STR_HEAVY_LASER")),
        Research("STR_MOTION_SCANNER", "Motion Scanner", 60),
        Research("STR_MEDI_KIT", "Medi-Kit", 60),
        # Tier 0.5 — derived from Laser Weapons
        Research("STR_LASER_PISTOL", "Laser Pistol", 80,
                 prerequisites=("STR_LASER_WEAPONS",),
                 grants_item="laser_pistol"),
        Research("STR_LASER_RIFLE", "Laser Rifle", 120,
                 prerequisites=("STR_LASER_WEAPONS",),
                 grants_item="laser_rifle"),
        Research("STR_HEAVY_LASER", "Heavy Laser", 160,
                 prerequisites=("STR_LASER_WEAPONS",),
                 grants_item="heavy_laser"),
        # Tier 1 — needs live alien + corpse
        Research("STR_ALIEN_ORIGINS", "Alien Origins", 240,
                 prerequisites=("STR_SECTOID_LEADER",),
                 unlocks=("STR_THE_MARTIAN_SOLUTION",)),
        Research("STR_THE_MARTIAN_SOLUTION", "The Martian Solution", 360,
                 prerequisites=("STR_ALIEN_ORIGINS",),
                 unlocks=("STR_CYDONIA_OR_BUST",)),
        Research("STR_CYDONIA_OR_BUST", "Cydonia or Bust", 400,
                 prerequisites=("STR_THE_MARTIAN_SOLUTION",)),
        # Tier 1.5 — alien tech
        Research("STR_ALIEN_ALLOYS", "Alien Alloys", 180),
        Research("STR_PLASMA_PISTOL", "Plasma Pistol", 160,
                 prerequisites=("STR_ALIEN_ALLOYS",),
                 grants_item="plasma_pistol"),
        Research("STR_PLASMA_RIFLE", "Plasma Rifle", 200,
                 prerequisites=("STR_ALIEN_ALLOYS",),
                 grants_item="plasma_rifle"),
        Research("STR_HEAVY_PLASMA", "Heavy Plasma", 280,
                 prerequisites=("STR_ALIEN_ALLOYS",),
                 grants_item="heavy_plasma"),
        Research("STR_ELERIUM_115", "Elerium-115", 120,
                 prerequisites=("STR_ALIEN_ALLOYS",)),
        # Craft tech
        Research("STR_NEW_FIGHTER_CRAFT", "New Fighter Craft", 340,
                 prerequisites=("STR_ALIEN_ALLOYS", "STR_ELERIUM_115"),
                 grants_item="firestorm"),
        Research("STR_NEW_FIGHTER_TRANSPORTER",
                 "New Fighter-Transporter", 420,
                 prerequisites=("STR_NEW_FIGHTER_CRAFT",),
                 grants_item="lightning"),
        Research("STR_ULTIMATE_CRAFT", "Ultimate Craft", 500,
                 prerequisites=("STR_NEW_FIGHTER_TRANSPORTER",),
                 grants_item="avenger"),
        # Captive interrogations (alien ranks)
        Research("STR_SECTOID_SOLDIER", "Sectoid Soldier", 50),
        Research("STR_SECTOID_NAVIGATOR", "Sectoid Navigator", 80,
                 unlocks=("STR_HYPER_WAVE_DECODER",)),
        Research("STR_SECTOID_LEADER", "Sectoid Leader", 100,
                 prerequisites=("STR_SECTOID_NAVIGATOR",)),
        Research("STR_SECTOID_COMMANDER", "Sectoid Commander", 130,
                 prerequisites=("STR_SECTOID_LEADER",),
                 unlocks=("STR_ALIEN_ORIGINS",)),
        Research("STR_HYPER_WAVE_DECODER", "Hyper-Wave Decoder", 260,
                 prerequisites=("STR_SECTOID_NAVIGATOR",),
                 grants_item="hyper_wave_decoder"),
        # Armor
        Research("STR_PERSONAL_ARMOR", "Personal Armor", 180,
                 prerequisites=("STR_ALIEN_ALLOYS",),
                 grants_item="personal_armor"),
        Research("STR_POWER_SUIT", "Power Suit", 400,
                 prerequisites=("STR_PERSONAL_ARMOR",),
                 grants_item="power_suit"),
        Research("STR_FLYING_SUIT", "Flying Suit", 450,
                 prerequisites=("STR_POWER_SUIT",),
                 grants_item="flying_suit"),
    ]
}


# ---- items (manufactureable) -------------------------------------------

@dataclass(frozen=True)
class Item:
    id: str
    name: str
    category: str                # "weapon" | "armor" | "craft" | "facility"
    build_cost: int = 0          # engineer-hours
    dollar_cost: int = 0         # $ per unit
    sell_price: int = 0          # $ if sold
    requires: tuple[str, ...] = ()  # research id prereqs


ITEMS: dict[str, Item] = {i.id: i for i in [
    # Conventional weapons (shipped researched)
    Item("pistol", "Pistol", "weapon", 0, 800, 400),
    Item("rifle", "Rifle", "weapon", 0, 3000, 1500),
    Item("heavy_cannon", "Heavy Cannon", "weapon", 0, 6400, 3200),
    Item("grenade", "Grenade", "weapon", 0, 300, 150),
    # Laser weapons
    Item("laser_pistol", "Laser Pistol", "weapon", 300, 8000, 4000,
         requires=("STR_LASER_PISTOL",)),
    Item("laser_rifle", "Laser Rifle", "weapon", 700, 20000, 10000,
         requires=("STR_LASER_RIFLE",)),
    Item("heavy_laser", "Heavy Laser", "weapon", 1000, 32000, 16000,
         requires=("STR_HEAVY_LASER",)),
    # Plasma weapons
    Item("plasma_pistol", "Plasma Pistol", "weapon", 800, 18000, 9000,
         requires=("STR_PLASMA_PISTOL",)),
    Item("plasma_rifle", "Plasma Rifle", "weapon", 1200, 38000, 19000,
         requires=("STR_PLASMA_RIFLE",)),
    Item("heavy_plasma", "Heavy Plasma", "weapon", 1400, 56000, 28000,
         requires=("STR_HEAVY_PLASMA",)),
    # Armor
    Item("personal_armor", "Personal Armor", "armor", 800, 22000, 11000,
         requires=("STR_PERSONAL_ARMOR",)),
    Item("power_suit", "Power Suit", "armor", 1200, 56000, 28000,
         requires=("STR_POWER_SUIT",)),
    Item("flying_suit", "Flying Suit", "armor", 1400, 72000, 36000,
         requires=("STR_FLYING_SUIT",)),
    # Craft
    Item("firestorm", "Firestorm", "craft", 1000, 400000, 0,
         requires=("STR_NEW_FIGHTER_CRAFT",)),
    Item("lightning", "Lightning", "craft", 1400, 600000, 0,
         requires=("STR_NEW_FIGHTER_TRANSPORTER",)),
    Item("avenger", "Avenger", "craft", 1800, 900000, 0,
         requires=("STR_ULTIMATE_CRAFT",)),
    # Facilities
    Item("facility_laser_defense", "Laser Defense", "facility", 600, 150000, 0,
         requires=("STR_LASER_WEAPONS",)),
    Item("facility_hyper_wave", "Hyper-Wave Decoder", "facility", 800, 450000, 0,
         requires=("STR_HYPER_WAVE_DECODER",)),
]}


# ---- craft --------------------------------------------------------------

@dataclass(frozen=True)
class CraftType:
    id: str
    name: str
    speed_kph: int                 # cruise speed
    max_fuel: int
    max_damage: int
    soldier_capacity: int          # 0 for interceptor-only
    weapon_slots: int
    purchase_price: int = 0        # $ to buy (0 if research-gated)


CRAFT_TYPES: dict[str, CraftType] = {c.id: c for c in [
    CraftType("skyranger", "Skyranger", 760, 1500, 150, 14, 0, 500000),
    CraftType("interceptor", "Interceptor", 2100, 1000, 100, 0, 2, 600000),
    CraftType("firestorm", "Firestorm", 4200, 2000, 200, 0, 2),
    CraftType("lightning", "Lightning", 3100, 2000, 200, 12, 1),
    CraftType("avenger", "Avenger", 5400, 2000, 300, 26, 2),
]}


# ---- UFOs ---------------------------------------------------------------

@dataclass(frozen=True)
class UfoType:
    id: str
    name: str
    speed_kph: int
    max_damage: int
    crew_size: int
    score_on_shoot_down: int
    glyph: str


UFO_TYPES: dict[str, UfoType] = {u.id: u for u in [
    UfoType("small_scout", "Small Scout", 2200, 50, 2, 50, "s"),
    UfoType("medium_scout", "Medium Scout", 2400, 200, 5, 75, "m"),
    UfoType("large_scout", "Large Scout", 2700, 250, 8, 125, "L"),
    UfoType("harvester", "Harvester", 2300, 500, 12, 250, "H"),
    UfoType("abductor", "Abductor", 2600, 500, 13, 275, "A"),
    UfoType("terror_ship", "Terror Ship", 2400, 1200, 17, 400, "T"),
    UfoType("battleship", "Battleship", 2100, 3200, 22, 700, "B"),
]}


# ---- aliens -------------------------------------------------------------

@dataclass(frozen=True)
class AlienRank:
    id: str
    name: str
    glyph: str                     # 1-cell symbol for battlescape
    hp: int
    tu: int                        # time units
    firing_accuracy: int           # %
    research_on_capture: str = ""  # research id unlocked by interrogation


ALIEN_RANKS: dict[str, AlienRank] = {a.id: a for a in [
    AlienRank("sectoid_soldier", "Sectoid Soldier", "s", 30, 54, 52,
              research_on_capture="STR_SECTOID_SOLDIER"),
    AlienRank("sectoid_navigator", "Sectoid Navigator", "n", 30, 56, 60,
              research_on_capture="STR_SECTOID_NAVIGATOR"),
    AlienRank("sectoid_leader", "Sectoid Leader", "l", 35, 58, 65,
              research_on_capture="STR_SECTOID_LEADER"),
    AlienRank("sectoid_commander", "Sectoid Commander", "c", 45, 64, 72,
              research_on_capture="STR_SECTOID_COMMANDER"),
    AlienRank("floater_soldier", "Floater Soldier", "f", 40, 50, 48, ""),
    AlienRank("muton_soldier", "Muton Soldier", "M", 125, 66, 60, ""),
    AlienRank("cyberdisc", "Cyberdisc", "◉", 120, 70, 65, ""),
    AlienRank("chryssalid", "Chryssalid", "C", 80, 110, 0, ""),  # melee
]}


# ---- facilities (base interior) ----------------------------------------

@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    glyph: str
    build_days: int
    build_cost: int
    monthly_cost: int
    capacity: int = 0              # beds / lab space / workshop space / storage
    category: str = "utility"      # "living" | "lab" | "shop" | "hangar" | "utility"
    requires: tuple[str, ...] = ()


FACILITIES: dict[str, Facility] = {f.id: f for f in [
    Facility("access_lift",   "Access Lift",       "A", 1, 300000, 4000, 0, "utility"),
    Facility("living_q",      "Living Quarters",   "L", 16, 400000, 10000, 50, "living"),
    Facility("laboratory",    "Laboratory",        "B", 26, 750000, 30000, 50, "lab"),
    Facility("workshop",      "Workshop",          "W", 32, 800000, 35000, 50, "shop"),
    Facility("small_radar",   "Small Radar System","r", 12, 500000, 10000, 0, "utility"),
    Facility("large_radar",   "Large Radar System","R", 25, 800000, 15000, 0, "utility"),
    Facility("hangar",        "Hangar",            "H", 25, 200000, 25000, 1, "hangar"),
    Facility("general_store", "General Stores",    "S", 10, 150000, 5000, 50, "utility"),
    Facility("alien_contain", "Alien Containment", "C", 18, 400000, 15000, 10, "utility",
             requires=("STR_SECTOID_SOLDIER",)),
    Facility("psi_lab",       "Psi Lab",           "Ψ", 40, 750000, 34000, 10, "lab",
             requires=("STR_SECTOID_COMMANDER",)),
    Facility("hyper_wave",    "Hyper-Wave Decoder","Y", 26, 1400000, 30000, 0, "utility",
             requires=("STR_HYPER_WAVE_DECODER",)),
    Facility("laser_defense", "Laser Defense",     "D", 24, 500000, 15000, 0, "utility",
             requires=("STR_LASER_WEAPONS",)),
]}


# ---- starting inventory / constants ------------------------------------

STARTING_FUNDS = 6_000_000
STARTING_SOLDIERS = 8
STARTING_SCIENTISTS = 10
STARTING_ENGINEERS = 10
STARTING_SCIENTIST_COST = 30_000
STARTING_ENGINEER_COST = 25_000
STARTING_SOLDIER_COST = 20_000

# Country funding (simplified — 16 countries from the original, monthly
# contribution in $). Total ≈ starting world council monthly income.
COUNTRY_FUNDING: dict[str, int] = {
    "USA": 1_000_000, "Russia": 700_000, "UK": 500_000,
    "France": 500_000, "Germany": 500_000, "Italy": 350_000,
    "Spain": 300_000, "China": 400_000, "Japan": 500_000,
    "Canada": 350_000, "India": 300_000, "Brazil": 350_000,
    "Egypt": 250_000, "Nigeria": 250_000, "SouthAfrica": 250_000,
    "Australia": 400_000,
}

# Rough country lat/lon (for geoscape rendering + incident scoring).
COUNTRY_CENTRES: dict[str, tuple[float, float]] = {
    "USA":          ( 40.0, -100.0),
    "Russia":       ( 60.0,   90.0),
    "UK":           ( 54.0,   -2.0),
    "France":       ( 46.0,    2.0),
    "Germany":      ( 51.0,   10.0),
    "Italy":        ( 42.0,   12.0),
    "Spain":        ( 40.0,   -3.0),
    "China":        ( 35.0,  105.0),
    "Japan":        ( 36.0,  138.0),
    "Canada":       ( 60.0,  -95.0),
    "India":        ( 22.0,   78.0),
    "Brazil":       (-14.0,  -53.0),
    "Egypt":        ( 26.0,   30.0),
    "Nigeria":      (  9.0,    8.0),
    "SouthAfrica":  (-30.0,   24.0),
    "Australia":    (-25.0,  135.0),
}


# ---- optional vendor data augment --------------------------------------

def augment_from_vendor(vendor_root: Path) -> int:
    """If the OXC upstream is vendored, pull additional research entries
    from ``bin/standard/xcom1/research.rul`` and merge them into
    RESEARCH (without overriding existing IDs). Returns the number of
    entries added. Best-effort — silently skips on missing file / YAML
    parse error.

    Intentionally lazy-imports yaml so the test suite works without
    pyyaml installed."""
    path = vendor_root / "bin" / "standard" / "xcom1" / "research.rul"
    if not path.exists():
        return 0
    try:
        import yaml  # type: ignore
    except ImportError:
        return 0
    try:
        data = yaml.safe_load(path.read_text())
    except Exception:
        return 0
    added = 0
    for entry in data.get("research", []):
        rid = entry.get("name") or entry.get("id")
        if not rid or rid in RESEARCH:
            continue
        cost = int(entry.get("cost", 100))
        prereqs = tuple(entry.get("dependencies", []) or ())
        RESEARCH[rid] = Research(rid, rid.replace("STR_", "").replace("_", " ").title(),
                                 cost, prereqs)
        added += 1
    return added


# ---- accessors ---------------------------------------------------------

def research_list() -> list[Research]:
    return list(RESEARCH.values())


def available_research(completed: Iterable[str]) -> list[Research]:
    """Research that's been unlocked (all prereqs completed) but not yet
    finished."""
    done = set(completed)
    out = []
    for r in RESEARCH.values():
        if r.id in done:
            continue
        if all(p in done for p in r.prerequisites):
            out.append(r)
    return out


def manufacturable_items(completed: Iterable[str]) -> list[Item]:
    done = set(completed)
    return [
        i for i in ITEMS.values()
        if i.build_cost > 0 and all(r in done for r in i.requires)
    ]
