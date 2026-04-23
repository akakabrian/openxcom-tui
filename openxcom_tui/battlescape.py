"""Battlescape — tile-based tactical combat.

A minimal X-COM tactical mission:
  * 40×40 grid with mixed terrain (grass / dirt / tree / wall / door).
  * Player + alien units, each with HP, TU, firing accuracy.
  * Actions: move (1 TU / tile), snap shot (25% TU), aimed shot (60% TU),
    end turn. Moving through other units is blocked; diagonal moves
    cost 1.5 TU (simplified to 2).
  * Line-of-sight via a cheap Bresenham + wall blocker.
  * Alien AI: walk toward nearest visible player unit; if in LOS and
    has TU, take a snap shot.

Tiny compared to OpenXcom's real battlescape (no reaction fire, no
throwing, no inventory management, no psi, no smoke / fire, no
multi-level Z). Intentional — MVP.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import content


BATTLE_W = 40
BATTLE_H = 40


# Terrain tile classes
# ``wall`` and ``tree`` block sight + movement; ``door`` blocks movement
# until opened; ``dirt`` / ``grass`` / ``floor`` are open.
TERRAIN_CLASSES = {
    "grass", "dirt", "tree", "wall", "floor",
    "door_closed", "door_open", "water", "rubble",
}
BLOCKED_MOVE = {"wall", "tree", "water", "door_closed"}
BLOCKED_SIGHT = {"wall", "tree"}


@dataclass
class Unit:
    id: int
    side: str                      # "player" | "alien"
    x: int
    y: int
    hp: int
    max_hp: int
    tu: int
    max_tu: int
    firing_accuracy: int
    name: str
    glyph: str = "@"
    soldier_id: int = 0            # maps back to Game.soldiers for player units
    rank_id: str = ""              # content.ALIEN_RANKS id for aliens
    alive: bool = True
    stunned: bool = False
    kills_this_mission: int = 0


@dataclass
class Battle:
    rng: random.Random
    terrain: list[list[str]]
    units: list[Unit]
    turn: str = "player"
    turn_number: int = 1
    selected_idx: int = 0
    score_victory: int = 0
    salvage_value: int = 0
    captives: dict[str, int] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    # UFO context — used to compute score/salvage on exit.
    ufo_type_id: str = "small_scout"

    # --- selection --------------------------------------------------------

    def player_units(self) -> list[Unit]:
        return [u for u in self.units if u.side == "player" and u.alive]

    def alien_units(self) -> list[Unit]:
        return [u for u in self.units if u.side == "alien" and u.alive]

    def selected(self) -> Optional[Unit]:
        pu = self.player_units()
        if not pu:
            return None
        self.selected_idx %= len(pu)
        return pu[self.selected_idx]

    def cycle_selection(self, direction: int = 1) -> None:
        pu = self.player_units()
        if not pu:
            return
        self.selected_idx = (self.selected_idx + direction) % len(pu)

    # --- geometry ---------------------------------------------------------

    def unit_at(self, x: int, y: int) -> Optional[Unit]:
        for u in self.units:
            if u.alive and u.x == x and u.y == y:
                return u
        return None

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < BATTLE_W and 0 <= y < BATTLE_H

    def tile(self, x: int, y: int) -> str:
        if not self.in_bounds(x, y):
            return "wall"
        return self.terrain[y][x]

    def can_enter(self, x: int, y: int, ignore_units: bool = False) -> bool:
        if not self.in_bounds(x, y):
            return False
        if self.tile(x, y) in BLOCKED_MOVE:
            return False
        if not ignore_units and self.unit_at(x, y) is not None:
            return False
        return True

    def line_of_sight(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        """Bresenham sight check: blocked only by intermediate walls / trees.
        Endpoints themselves are fine."""
        pts = _bresenham(x0, y0, x1, y1)
        for (x, y) in pts[1:-1]:  # skip endpoints
            if self.tile(x, y) in BLOCKED_SIGHT:
                return False
        return True

    # --- player actions ---------------------------------------------------

    def move_selected(self, dx: int, dy: int) -> str:
        u = self.selected()
        if u is None:
            return "no selection"
        nx, ny = u.x + dx, u.y + dy
        if not self.in_bounds(nx, ny):
            return "out of bounds"
        # Door interaction — step onto a closed door opens it (1 TU).
        t = self.tile(nx, ny)
        if t == "door_closed":
            if u.tu < 3:
                return "not enough TU to open door"
            u.tu -= 3
            self.terrain[ny][nx] = "door_open"
            self.log.append(f"{u.name} opens a door")
            return "opened door"
        if not self.can_enter(nx, ny):
            return "blocked"
        cost = 2 if (dx != 0 and dy != 0) else 1
        if u.tu < cost:
            return "not enough TU"
        u.tu -= cost
        u.x, u.y = nx, ny
        return "moved"

    def shoot_selected(self, tx: int, ty: int, mode: str = "snap") -> str:
        """Fire from selected unit at (tx, ty). `mode`: "snap" | "aimed" | "auto"."""
        u = self.selected()
        if u is None:
            return "no selection"
        if not self.in_bounds(tx, ty):
            return "out of bounds"
        tu_pct = {"snap": 0.25, "aimed": 0.60, "auto": 0.35}.get(mode, 0.25)
        acc_mod = {"snap": 1.0, "aimed": 1.5, "auto": 0.7}.get(mode, 1.0)
        tu_cost = int(u.max_tu * tu_pct)
        if u.tu < tu_cost:
            return "not enough TU"
        u.tu -= tu_cost
        if not self.line_of_sight(u.x, u.y, tx, ty):
            self.log.append(f"{u.name}: no line of sight")
            return "no LOS"
        # Distance penalty: accuracy drops 2% per tile past 10.
        dist = max(abs(u.x - tx), abs(u.y - ty))
        accuracy = int(u.firing_accuracy * acc_mod - max(0, dist - 10) * 2)
        shots = 3 if mode == "auto" else 1
        result = "miss"
        for _ in range(shots):
            if self.rng.randint(1, 100) <= max(5, accuracy):
                target = self.unit_at(tx, ty)
                damage = self.rng.randint(20, 40)
                if target is not None:
                    target.hp -= damage
                    if target.hp <= 0:
                        target.alive = False
                        self.log.append(f"{u.name} killed {target.name}")
                        u.kills_this_mission += 1
                    else:
                        self.log.append(
                            f"{u.name} hit {target.name} for {damage}"
                        )
                    result = "hit"
                else:
                    self.log.append(f"{u.name} shot impacts terrain")
                    result = "miss_terrain"
            else:
                self.log.append(f"{u.name} missed")
        return result

    def end_player_turn(self) -> list[str]:
        """Hand over to aliens. Runs their turn fully and resets player TU."""
        events: list[str] = []
        self.turn = "alien"
        events += _run_alien_turn(self)
        # Reset TU for surviving player units.
        for u in self.player_units():
            u.tu = u.max_tu
        self.turn = "player"
        self.turn_number += 1
        return events

    # --- state --------------------------------------------------------------

    def outcome(self) -> Optional[str]:
        """Return "victory" if all aliens dead, "defeat" if all players dead,
        else None."""
        if not self.alien_units():
            return "victory"
        if not self.player_units():
            return "defeat"
        return None

    def snapshot(self) -> dict:
        return {
            "turn": self.turn,
            "turn_number": self.turn_number,
            "selected_idx": self.selected_idx,
            "units": [
                {"id": u.id, "side": u.side, "x": u.x, "y": u.y,
                 "hp": u.hp, "max_hp": u.max_hp, "tu": u.tu, "max_tu": u.max_tu,
                 "name": u.name, "alive": u.alive, "glyph": u.glyph}
                for u in self.units
            ],
            "width": BATTLE_W, "height": BATTLE_H,
        }


# ---- construction --------------------------------------------------------

def new_battle(rng: random.Random, soldiers: Iterable, ufo_type_id: str = "small_scout"
               ) -> Battle:
    terrain = _generate_terrain(rng)
    units: list[Unit] = []
    uid = 1
    # Drop soldiers near the bottom edge (Skyranger landing zone).
    sx, sy = 5, BATTLE_H - 5
    from .engine import Soldier  # avoid circular at import-time
    soldier_list = [s for s in soldiers if isinstance(s, Soldier) and s.alive]
    for i, s in enumerate(soldier_list):
        x = sx + (i % 4)
        y = sy + (i // 4)
        # If terrain blocks, nudge.
        while terrain[y][x] in BLOCKED_MOVE:
            x += 1
            if x >= BATTLE_W - 2:
                x = sx
                y -= 1
        units.append(Unit(
            id=uid, side="player", x=x, y=y,
            hp=s.hp, max_hp=s.max_hp, tu=s.tu, max_tu=s.tu,
            firing_accuracy=s.firing_accuracy,
            name=s.name, glyph="@", soldier_id=s.id,
        ))
        uid += 1

    # Spawn aliens — number scales with UFO size.
    alien_counts = {
        "small_scout": 2, "medium_scout": 4, "large_scout": 6,
        "harvester": 8, "abductor": 8, "terror_ship": 10, "battleship": 12,
    }
    n_aliens = alien_counts.get(ufo_type_id, 4)
    rank_pool = ["sectoid_soldier", "sectoid_soldier", "sectoid_navigator",
                 "sectoid_leader", "floater_soldier"]
    for i in range(n_aliens):
        rid = rng.choice(rank_pool)
        rank = content.ALIEN_RANKS[rid]
        # Aliens cluster around top-middle of the map (UFO landing).
        while True:
            x = rng.randint(12, BATTLE_W - 3)
            y = rng.randint(3, 12)
            if terrain[y][x] not in BLOCKED_MOVE:
                break
        units.append(Unit(
            id=uid, side="alien", x=x, y=y,
            hp=rank.hp, max_hp=rank.hp, tu=rank.tu, max_tu=rank.tu,
            firing_accuracy=rank.firing_accuracy,
            name=rank.name, glyph=rank.glyph, rank_id=rid,
        ))
        uid += 1

    score = {"small_scout": 50, "medium_scout": 80, "large_scout": 140,
             "harvester": 220, "abductor": 240, "terror_ship": 380,
             "battleship": 600}.get(ufo_type_id, 80)
    salvage = score * 1000
    return Battle(rng=rng, terrain=terrain, units=units,
                  score_victory=score, salvage_value=salvage,
                  ufo_type_id=ufo_type_id)


def _generate_terrain(rng: random.Random) -> list[list[str]]:
    """Hand-rolled farm + UFO tileset. Grass all over, a cluster of trees,
    a rectangular 'farmhouse' with walls + a door, a small pond."""
    terrain = [["grass" for _ in range(BATTLE_W)] for _ in range(BATTLE_H)]
    # Tree clumps.
    for _ in range(60):
        x = rng.randint(0, BATTLE_W - 1)
        y = rng.randint(0, BATTLE_H - 1)
        if rng.random() < 0.5 and 3 < y < BATTLE_H - 3:
            terrain[y][x] = "tree"
    # Dirt patches.
    for _ in range(30):
        cx = rng.randint(2, BATTLE_W - 3)
        cy = rng.randint(2, BATTLE_H - 3)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if 0 <= cx + dx < BATTLE_W and 0 <= cy + dy < BATTLE_H:
                    if terrain[cy + dy][cx + dx] == "grass" and rng.random() < 0.5:
                        terrain[cy + dy][cx + dx] = "dirt"
    # Farmhouse — 6×5 walls with a door on the south side, floor inside.
    fx, fy = 25, 18
    for x in range(fx, fx + 6):
        for y in range(fy, fy + 5):
            terrain[y][x] = "floor"
    for x in range(fx, fx + 6):
        terrain[fy][x] = "wall"
        terrain[fy + 4][x] = "wall"
    for y in range(fy, fy + 5):
        terrain[y][fx] = "wall"
        terrain[y][fx + 5] = "wall"
    terrain[fy + 4][fx + 2] = "door_closed"
    # Small pond.
    pond_cx, pond_cy = 8, 14
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if dx * dx + dy * dy <= 4:
                terrain[pond_cy + dy][pond_cx + dx] = "water"
    # UFO hull — 3×3 rubble-ish at the top of the map.
    ux, uy = BATTLE_W // 2 - 1, 4
    for dx in range(-2, 3):
        for dy in range(-1, 2):
            terrain[uy + dy][ux + dx] = "floor"
    for dx in range(-2, 3):
        terrain[uy - 1][ux + dx] = "wall"
        terrain[uy + 1][ux + dx] = "wall"
    for dy in range(-1, 2):
        terrain[uy + dy][ux - 2] = "wall"
        terrain[uy + dy][ux + 2] = "wall"
    terrain[uy + 1][ux] = "door_open"
    return terrain


# ---- alien AI ------------------------------------------------------------

def _run_alien_turn(b: Battle) -> list[str]:
    """One pass of alien turns. Each alien: move toward closest visible
    player unit; if LOS + TU, take a snap shot."""
    events: list[str] = []
    for a in b.alien_units():
        if not a.alive:
            continue
        # Find closest alive player unit.
        closest: Optional[Unit] = None
        best_d = 1e9
        for p in b.player_units():
            d = max(abs(a.x - p.x), abs(a.y - p.y))
            if d < best_d:
                best_d = d
                closest = p
        if closest is None:
            continue
        # Try to shoot if LOS and enough TU.
        if b.line_of_sight(a.x, a.y, closest.x, closest.y):
            shot_cost = int(a.max_tu * 0.25)
            if a.tu >= shot_cost:
                a.tu -= shot_cost
                if b.rng.randint(1, 100) <= max(5, a.firing_accuracy - max(0, best_d - 10) * 2):
                    dmg = b.rng.randint(15, 35)
                    closest.hp -= dmg
                    events.append(f"[alien] {a.name} hit {closest.name} for {dmg}")
                    if closest.hp <= 0:
                        closest.alive = False
                        events.append(f"[alien] {closest.name} killed")
                else:
                    events.append(f"[alien] {a.name} missed {closest.name}")
                continue  # don't also move after shooting
        # Otherwise step toward the target.
        steps = 0
        while a.tu >= 1 and steps < 3:
            dx = 0 if a.x == closest.x else (1 if closest.x > a.x else -1)
            dy = 0 if a.y == closest.y else (1 if closest.y > a.y else -1)
            if (dx, dy) == (0, 0):
                break
            nx, ny = a.x + dx, a.y + dy
            if b.can_enter(nx, ny):
                cost = 2 if (dx != 0 and dy != 0) else 1
                if a.tu < cost:
                    break
                a.tu -= cost
                a.x, a.y = nx, ny
            else:
                # Try orthogonal fallback.
                if dx and b.can_enter(a.x + dx, a.y):
                    a.tu -= 1
                    a.x += dx
                elif dy and b.can_enter(a.x, a.y + dy):
                    a.tu -= 1
                    a.y += dy
                else:
                    break
            steps += 1
    # Capture-check: aliens that end turn stunned become captives if the
    # player wins. We don't model stun directly in MVP, but the logic is
    # here for future extension.
    return events


# ---- utilities -----------------------------------------------------------

def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Integer Bresenham line — used for LOS checks."""
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points
