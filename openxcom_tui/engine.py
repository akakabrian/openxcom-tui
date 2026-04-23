"""Game engine — geoscape + base management state.

Pure-Python sim inspired by OpenXcom's architecture. See DECISIONS.md
for the rationale (no SWIG, no subprocess, no vendor asset requirement).

The authoritative game state is the ``Game`` dataclass; everything else
(base, craft, UFO, research / manufacture projects) hangs off it. The
Textual app and the agent REST API both read from / mutate this single
object — never forking state — so a snapshot is always consistent.

Time:
  * In-game time is tracked in *hours*. ``advance_hours(n)`` is the
    primitive tick; ``advance_day()`` is 24 of those. The TUI wires the
    fast tick (5-min game-time per real second) on a Textual
    ``set_interval`` timer.
  * A *month* event fires whenever ``game.hour // 720`` advances — this
    triggers country funding, scientist / engineer upkeep, and the
    Council report.

Battlescape:
  * ``start_battle(ufo=None)`` creates a ``Battle`` attached to
    ``game.battle`` and tags the mode as BATTLE. The app swaps to the
    BattlescapeScreen on that transition.
  * ``end_battle(outcome)`` resolves results into the geoscape (salvage,
    score, soldier casualties, captive aliens).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from . import content

if TYPE_CHECKING:
    from .battlescape import Battle


# ---- geoscape tick constants ---------------------------------------------

HOURS_PER_DAY = 24
HOURS_PER_MONTH = 720       # 30-day months, faithful to OXC
DAYS_PER_MONTH = 30
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# World grid rendered as Mercator ASCII. Globe is wrap-around in X,
# clamped in Y. These dims are the *render* size — the underlying lat/lon
# is continuous (floats).
GEO_W = 120
GEO_H = 36


class Mode(Enum):
    GEOSCAPE = "geoscape"
    BATTLE = "battle"
    GAME_OVER = "game_over"


# ---- basic entities ------------------------------------------------------

@dataclass
class Soldier:
    id: int
    name: str
    hp: int = 40
    max_hp: int = 40
    tu: int = 60            # max time units
    firing_accuracy: int = 55
    throwing_accuracy: int = 50
    strength: int = 25
    bravery: int = 30
    missions: int = 0
    kills: int = 0
    alive: bool = True


@dataclass
class CraftInstance:
    id: int
    type_id: str
    base_idx: int            # which base it belongs to
    name: str
    fuel: int
    damage: int = 0
    status: str = "ready"    # ready | out | refuel | repair | intercepting
    weapons: list[str] = field(default_factory=list)
    soldier_ids: list[int] = field(default_factory=list)
    # Position while out (lat/lon). None while in base.
    lat: float | None = None
    lon: float | None = None
    target_ufo_id: Optional[int] = None


@dataclass
class UFOInstance:
    id: int
    type_id: str
    lat: float
    lon: float
    heading: float           # radians; 0 = east
    speed_kph: int
    detected: bool = False
    shot_down: bool = False
    hp: int = 100
    # Ticks until despawn if not intercepted. Drops to 0 → UFO leaves.
    ttl_hours: int = 96


@dataclass
class ResearchProject:
    id: str                  # matches content.RESEARCH id
    progress: int = 0        # scientist-hours accrued
    assigned: int = 0        # scientists allocated
    completed: bool = False


@dataclass
class ManufactureProject:
    id: str                  # matches content.ITEMS id
    quantity: int = 1
    produced: int = 0
    progress_hours: int = 0  # engineer-hours on current unit
    assigned: int = 0        # engineers allocated


@dataclass
class FacilityInstance:
    id: str                  # content.FACILITIES id
    x: int
    y: int
    days_left: int = 0       # > 0 while under construction


@dataclass
class Base:
    name: str
    lat: float
    lon: float
    # 6x6 interior grid; dict of (x,y) -> FacilityInstance
    facilities: dict[tuple[int, int], FacilityInstance] = field(default_factory=dict)
    scientists: int = content.STARTING_SCIENTISTS
    engineers: int = content.STARTING_ENGINEERS
    soldier_ids: list[int] = field(default_factory=list)
    stores: dict[str, int] = field(default_factory=dict)   # item_id -> count
    alien_captives: dict[str, int] = field(default_factory=dict)

    # --- helpers
    def lab_capacity(self) -> int:
        return sum(content.FACILITIES[f.id].capacity
                   for f in self.facilities.values()
                   if content.FACILITIES[f.id].category == "lab" and f.days_left == 0)

    def workshop_capacity(self) -> int:
        return sum(content.FACILITIES[f.id].capacity
                   for f in self.facilities.values()
                   if content.FACILITIES[f.id].category == "shop" and f.days_left == 0)

    def living_capacity(self) -> int:
        return sum(content.FACILITIES[f.id].capacity
                   for f in self.facilities.values()
                   if content.FACILITIES[f.id].category == "living" and f.days_left == 0)

    def hangar_capacity(self) -> int:
        return sum(content.FACILITIES[f.id].capacity
                   for f in self.facilities.values()
                   if content.FACILITIES[f.id].category == "hangar" and f.days_left == 0)

    def radar_range_km(self) -> int:
        # Sum of radar ranges, dumbed down to one number for the globe
        # overlay. Small radar = 3000 km, large = 4500 km.
        rng = 0
        for f in self.facilities.values():
            if f.days_left > 0:
                continue
            if f.id == "small_radar":
                rng = max(rng, 3000)
            elif f.id in ("large_radar", "hyper_wave"):
                rng = max(rng, 4500)
        return rng


# ---- the top-level game object -------------------------------------------

@dataclass
class Game:
    seed: int = 0
    rng: random.Random = field(default_factory=random.Random)
    mode: Mode = Mode.GEOSCAPE
    funds: int = content.STARTING_FUNDS
    score: int = 0
    hour: int = 0            # total in-game hours since start
    paused: bool = False

    bases: list[Base] = field(default_factory=list)
    soldiers: dict[int, Soldier] = field(default_factory=dict)
    crafts: dict[int, CraftInstance] = field(default_factory=dict)
    ufos: dict[int, UFOInstance] = field(default_factory=dict)

    research_queue: list[ResearchProject] = field(default_factory=list)
    completed_research: set[str] = field(default_factory=set)
    manufacture_queue: list[ManufactureProject] = field(default_factory=list)

    log: list[str] = field(default_factory=list)

    # Monthly history, for graphs. One entry per month-end tick.
    history_funds: list[int] = field(default_factory=list)
    history_score: list[int] = field(default_factory=list)

    # Battlescape — None unless a mission is active. Forward-declared; real
    # class is in battlescape.py (imported lazily to avoid circular dep).
    battle: Optional["Battle"] = None

    # Counters for ID allocation.
    _next_soldier_id: int = 1
    _next_craft_id: int = 1
    _next_ufo_id: int = 1

    # --- lifecycle ---------------------------------------------------------

    def log_msg(self, s: str) -> None:
        """Append a message to the rolling log. Cap at 500 to bound memory."""
        self.log.append(s)
        if len(self.log) > 500:
            del self.log[:100]

    def day(self) -> int:
        return self.hour // HOURS_PER_DAY

    def month_index(self) -> int:
        return self.hour // HOURS_PER_MONTH

    def date_str(self) -> str:
        """Human date: e.g. 'Jan 15 1999, 08:00'."""
        m = self.month_index() % 12
        y = 1999 + self.month_index() // 12
        day_in_month = (self.day() % DAYS_PER_MONTH) + 1
        hour_in_day = self.hour % HOURS_PER_DAY
        return f"{MONTHS[m]} {day_in_month:02d} {y}, {hour_in_day:02d}:00"

    # --- construction ------------------------------------------------------

    def new_soldier(self, name: str | None = None, base_idx: int = 0) -> Soldier:
        sid = self._next_soldier_id
        self._next_soldier_id += 1
        n = name or _rand_soldier_name(self.rng)
        s = Soldier(
            id=sid, name=n,
            hp=40 + self.rng.randint(-5, 15),
            max_hp=40 + self.rng.randint(-5, 15),
            tu=50 + self.rng.randint(0, 20),
            firing_accuracy=45 + self.rng.randint(0, 30),
            throwing_accuracy=40 + self.rng.randint(0, 20),
            strength=20 + self.rng.randint(0, 20),
            bravery=10 + self.rng.randint(0, 50),
        )
        self.soldiers[sid] = s
        if 0 <= base_idx < len(self.bases):
            self.bases[base_idx].soldier_ids.append(sid)
        return s

    def new_craft(self, type_id: str, base_idx: int, name: str | None = None) -> CraftInstance:
        cid = self._next_craft_id
        self._next_craft_id += 1
        ct = content.CRAFT_TYPES[type_id]
        c = CraftInstance(
            id=cid, type_id=type_id, base_idx=base_idx,
            name=name or f"{ct.name}-{cid}",
            fuel=ct.max_fuel,
        )
        self.crafts[cid] = c
        return c

    def new_ufo(self, type_id: str, lat: float, lon: float) -> UFOInstance:
        uid = self._next_ufo_id
        self._next_ufo_id += 1
        ut = content.UFO_TYPES[type_id]
        u = UFOInstance(
            id=uid, type_id=type_id, lat=lat, lon=lon,
            heading=self.rng.uniform(0, 6.283),
            speed_kph=ut.speed_kph,
            hp=ut.max_damage,
            ttl_hours=24 * self.rng.randint(2, 5),
        )
        self.ufos[uid] = u
        return u

    # --- research ----------------------------------------------------------

    def start_research(self, research_id: str, assigned: int = 1) -> bool:
        if research_id not in content.RESEARCH:
            return False
        if research_id in self.completed_research:
            return False
        # Prereqs check.
        r = content.RESEARCH[research_id]
        if not all(p in self.completed_research for p in r.prerequisites):
            return False
        # Already in queue?
        for p in self.research_queue:
            if p.id == research_id:
                p.assigned = max(1, assigned)
                return True
        proj = ResearchProject(id=research_id, assigned=max(1, assigned))
        self.research_queue.append(proj)
        self.log_msg(f"[research] started {r.name}")
        return True

    def cancel_research(self, research_id: str) -> bool:
        before = len(self.research_queue)
        self.research_queue = [p for p in self.research_queue if p.id != research_id]
        return len(self.research_queue) < before

    # --- manufacture -------------------------------------------------------

    def start_manufacture(self, item_id: str, quantity: int = 1,
                           assigned: int = 1) -> bool:
        if item_id not in content.ITEMS:
            return False
        item = content.ITEMS[item_id]
        if not all(r in self.completed_research for r in item.requires):
            return False
        if item.build_cost <= 0:
            return False
        proj = ManufactureProject(id=item_id, quantity=quantity,
                                  assigned=max(1, assigned))
        self.manufacture_queue.append(proj)
        self.log_msg(f"[mfg] started {item.name} ×{quantity}")
        return True

    def cancel_manufacture(self, item_id: str) -> bool:
        before = len(self.manufacture_queue)
        self.manufacture_queue = [p for p in self.manufacture_queue if p.id != item_id]
        return len(self.manufacture_queue) < before

    # --- tick --------------------------------------------------------------

    def advance_hours(self, n: int = 1) -> list[str]:
        """Advance the sim ``n`` hours. Returns any events produced."""
        events: list[str] = []
        if self.paused or self.mode != Mode.GEOSCAPE:
            return events
        for _ in range(n):
            self.hour += 1
            events += _tick_research(self)
            events += _tick_manufacture(self)
            events += _tick_construction(self)
            events += _tick_ufos(self)
            if self.hour % HOURS_PER_MONTH == 0:
                events += _tick_month(self)
        for e in events:
            self.log_msg(e)
        return events

    def advance_day(self) -> list[str]:
        return self.advance_hours(HOURS_PER_DAY)

    # --- battle -----------------------------------------------------------

    def start_battle(self, ufo_id: int | None = None) -> "Battle":
        """Spin up a battlescape. Lazy-imports to avoid circular deps."""
        from .battlescape import new_battle
        base_idx = 0
        soldier_ids = list(self.bases[base_idx].soldier_ids) if self.bases else []
        # Take up to 8 soldiers on the mission, faithful to Skyranger.
        mission_soldiers = [self.soldiers[sid] for sid in soldier_ids[:8]
                            if self.soldiers[sid].alive]
        ufo_type = "small_scout"
        if ufo_id is not None and ufo_id in self.ufos:
            ufo_type = self.ufos[ufo_id].type_id
        battle = new_battle(self.rng, mission_soldiers, ufo_type)
        self.battle = battle
        self.mode = Mode.BATTLE
        self.log_msg(f"[battle] landing at {ufo_type} site")
        return battle

    def end_battle(self, victory: bool) -> list[str]:
        """Resolve a battle back into the geoscape."""
        events: list[str] = []
        b = self.battle
        if b is None:
            return events
        # Update soldier stats and casualties.
        for u in b.units:
            if u.side != "player":
                continue
            if u.soldier_id in self.soldiers:
                s = self.soldiers[u.soldier_id]
                s.missions += 1
                s.kills += u.kills_this_mission
                if u.hp <= 0:
                    s.alive = False
                    events.append(f"[kia] {s.name} killed in action")
                else:
                    s.hp = max(1, u.hp)
        # Score + salvage.
        if victory:
            self.score += b.score_victory
            self.funds += b.salvage_value
            events.append(
                f"[victory] +{b.score_victory} score, ${b.salvage_value:,} salvage"
            )
            # Live-alien captures unlock research.
            for rank_id, cnt in b.captives.items():
                if cnt <= 0:
                    continue
                # Add to base containment if available.
                if self.bases:
                    self.bases[0].alien_captives[rank_id] = (
                        self.bases[0].alien_captives.get(rank_id, 0) + cnt)
                rank = content.ALIEN_RANKS.get(rank_id)
                if rank and rank.research_on_capture and rank.research_on_capture not in self.completed_research:
                    # Seed a research project so it's visible to the player.
                    self.start_research(rank.research_on_capture, assigned=2)
        else:
            self.score -= 200
            events.append(f"[defeat] -200 score")
        self.battle = None
        self.mode = Mode.GEOSCAPE
        for e in events:
            self.log_msg(e)
        return events

    # --- serialization -----------------------------------------------------

    def state_snapshot(self) -> dict:
        """A read-only JSON-friendly snapshot for the agent API."""
        return {
            "mode": self.mode.value,
            "date": self.date_str(),
            "funds": self.funds,
            "score": self.score,
            "hour": self.hour,
            "paused": self.paused,
            "bases": [
                {
                    "name": b.name, "lat": b.lat, "lon": b.lon,
                    "scientists": b.scientists, "engineers": b.engineers,
                    "soldiers": len(b.soldier_ids),
                    "lab_capacity": b.lab_capacity(),
                    "workshop_capacity": b.workshop_capacity(),
                    "radar_range_km": b.radar_range_km(),
                    "facilities": [
                        {"id": f.id, "x": f.x, "y": f.y,
                         "days_left": f.days_left}
                        for f in b.facilities.values()
                    ],
                } for b in self.bases
            ],
            "research_queue": [
                {"id": p.id, "name": content.RESEARCH[p.id].name,
                 "cost": content.RESEARCH[p.id].cost,
                 "progress": p.progress, "assigned": p.assigned}
                for p in self.research_queue
            ],
            "completed_research": sorted(self.completed_research),
            "manufacture_queue": [
                {"id": p.id, "name": content.ITEMS[p.id].name,
                 "quantity": p.quantity, "produced": p.produced,
                 "assigned": p.assigned}
                for p in self.manufacture_queue
            ],
            "ufos": [
                {"id": u.id, "type": u.type_id, "lat": u.lat, "lon": u.lon,
                 "detected": u.detected, "shot_down": u.shot_down}
                for u in self.ufos.values()
            ],
            "soldiers": [
                {"id": s.id, "name": s.name, "hp": s.hp, "max_hp": s.max_hp,
                 "tu": s.tu, "firing": s.firing_accuracy, "kills": s.kills,
                 "missions": s.missions, "alive": s.alive}
                for s in self.soldiers.values()
            ],
            "battle": None if self.battle is None else self.battle.snapshot(),
        }


# ---- private tick helpers -----------------------------------------------

def _tick_research(g: Game) -> list[str]:
    events: list[str] = []
    # Each assigned scientist yields 1 progress-hour per game hour.
    done_ids: list[str] = []
    for proj in g.research_queue:
        # Clamp assigned by available scientists (first base for MVP).
        if g.bases:
            proj.assigned = min(proj.assigned, g.bases[0].scientists)
        proj.progress += proj.assigned
        r = content.RESEARCH[proj.id]
        # cost is in scientist-DAYS in content.py — convert to hours.
        if proj.progress >= r.cost * 24:
            done_ids.append(proj.id)
    for rid in done_ids:
        g.completed_research.add(rid)
        r = content.RESEARCH[rid]
        events.append(f"[research] completed {r.name}")
        # Keep scientists free for the next project.
        g.research_queue = [p for p in g.research_queue if p.id != rid]
    return events


def _tick_manufacture(g: Game) -> list[str]:
    events: list[str] = []
    for proj in list(g.manufacture_queue):
        if g.bases:
            proj.assigned = min(proj.assigned, g.bases[0].engineers)
        item = content.ITEMS[proj.id]
        proj.progress_hours += proj.assigned
        while proj.progress_hours >= item.build_cost and proj.produced < proj.quantity:
            proj.progress_hours -= item.build_cost
            proj.produced += 1
            # Deduct dollar cost, bump stores.
            g.funds -= item.dollar_cost
            if g.bases:
                g.bases[0].stores[proj.id] = g.bases[0].stores.get(proj.id, 0) + 1
            events.append(
                f"[mfg] produced {item.name} ({proj.produced}/{proj.quantity})"
            )
        if proj.produced >= proj.quantity:
            g.manufacture_queue = [p for p in g.manufacture_queue if p is not proj]
    return events


def _tick_construction(g: Game) -> list[str]:
    events: list[str] = []
    for b in g.bases:
        for f in b.facilities.values():
            if f.days_left > 0 and g.hour % HOURS_PER_DAY == 0:
                f.days_left -= 1
                if f.days_left == 0:
                    events.append(
                        f"[base] completed {content.FACILITIES[f.id].name} at ({f.x},{f.y})"
                    )
    return events


def _tick_ufos(g: Game) -> list[str]:
    events: list[str] = []
    # Rare UFO spawn: ~1 per 48h on average.
    if g.rng.random() < 1 / 48:
        types = list(content.UFO_TYPES.keys())
        # Weighted by month — early game mostly scouts, late game battleships.
        if g.month_index() < 2:
            candidates = ["small_scout", "small_scout", "medium_scout"]
        elif g.month_index() < 5:
            candidates = ["small_scout", "medium_scout", "large_scout", "harvester"]
        else:
            candidates = types
        kind = g.rng.choice(candidates)
        lat = g.rng.uniform(-60, 60)
        lon = g.rng.uniform(-180, 180)
        u = g.new_ufo(kind, lat, lon)
        events.append(f"[ufo] {content.UFO_TYPES[kind].name} spotted at "
                      f"({u.lat:+.0f},{u.lon:+.0f})")
    # Advance each UFO, detect, despawn.
    for u in list(g.ufos.values()):
        if u.shot_down:
            continue
        # Simple heading integration; 1 hour of flight.
        # km per hour → degrees; crude Earth (1 deg lat ≈ 111 km).
        dlat = math.sin(u.heading) * u.speed_kph / 111.0
        dlon = math.cos(u.heading) * u.speed_kph / 111.0 / max(0.3, math.cos(math.radians(u.lat)))
        u.lat = max(-80, min(80, u.lat + dlat))
        u.lon = ((u.lon + dlon + 180) % 360) - 180
        u.ttl_hours -= 1
        # Detection by base radar.
        if not u.detected:
            for b in g.bases:
                rng_km = b.radar_range_km()
                if rng_km <= 0:
                    continue
                # Great-circle approx via equirectangular.
                dx = (u.lon - b.lon) * 111 * math.cos(math.radians(b.lat))
                dy = (u.lat - b.lat) * 111
                d = (dx * dx + dy * dy) ** 0.5
                if d <= rng_km:
                    u.detected = True
                    events.append(
                        f"[radar] {content.UFO_TYPES[u.type_id].name} detected from {b.name}"
                    )
                    break
        if u.ttl_hours <= 0:
            events.append(
                f"[ufo] {content.UFO_TYPES[u.type_id].name} left the area"
            )
            del g.ufos[u.id]
    return events


def _tick_month(g: Game) -> list[str]:
    events: list[str] = []
    income = sum(content.COUNTRY_FUNDING.values())
    upkeep = 0
    for b in g.bases:
        upkeep += b.scientists * 30000
        upkeep += b.engineers * 25000
        upkeep += sum(content.FACILITIES[f.id].monthly_cost
                      for f in b.facilities.values() if f.days_left == 0)
    g.funds += income
    g.funds -= upkeep
    g.history_funds.append(g.funds)
    g.history_score.append(g.score)
    events.append(
        f"[council] Month {g.month_index()}: income ${income:,}, "
        f"upkeep ${upkeep:,}, balance ${g.funds:,}"
    )
    # Game over if broke for two consecutive months.
    if g.funds < -2_000_000:
        g.mode = Mode.GAME_OVER
        events.append("[council] Project X-COM terminated — insolvent.")
    return events


# ---- helpers -------------------------------------------------------------

_SOLDIER_FIRST = [
    "Alex", "Sam", "Jo", "Kai", "Rin", "Mika", "Nia", "Tom", "Ava",
    "Yuki", "Lars", "Noor", "Mei", "Omar", "Kim", "Fin", "Ira", "Tai",
]
_SOLDIER_LAST = [
    "Vega", "Park", "Cruz", "Bauer", "Sato", "Ng", "Oko", "Santos",
    "Rossi", "Volkov", "Khan", "Moss", "Reyes", "Lund", "Graf",
]


def _rand_soldier_name(rng: random.Random) -> str:
    return f"{rng.choice(_SOLDIER_FIRST)} {rng.choice(_SOLDIER_LAST)}"


# ---- starting state ------------------------------------------------------

def new_game(seed: int | None = None) -> Game:
    """Build a fresh game: one base in Europe, full starting staff,
    Skyranger + two Interceptors, 8 soldiers, no research in progress."""
    s = int(seed) if seed is not None else random.randint(0, 2**32 - 1)
    g = Game(seed=s, rng=random.Random(s))
    base = Base(name="Alpha", lat=47.0, lon=8.0)   # roughly Central Europe
    # Starting facilities — access lift + living quarters + lab + workshop +
    # small radar + two hangars + general stores. Mirrors OXC defaults.
    starters = [
        ("access_lift",   2, 2),
        ("living_q",      2, 1),
        ("laboratory",    1, 2),
        ("workshop",      3, 2),
        ("small_radar",   2, 3),
        ("general_store", 1, 3),
        ("hangar",        0, 0),
        ("hangar",        4, 0),
    ]
    for fid, x, y in starters:
        base.facilities[(x, y)] = FacilityInstance(id=fid, x=x, y=y, days_left=0)
    g.bases.append(base)
    for _ in range(content.STARTING_SOLDIERS):
        g.new_soldier(base_idx=0)
    g.new_craft("skyranger",   base_idx=0, name="Skyranger-1")
    g.new_craft("interceptor", base_idx=0, name="Interceptor-1")
    g.new_craft("interceptor", base_idx=0, name="Interceptor-2")
    g.log_msg(f"[start] Project X-COM online — base {base.name}, "
              f"${g.funds:,} starting funds")
    return g
