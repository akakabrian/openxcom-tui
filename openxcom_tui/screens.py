"""Modal screens — research queue, manufacture queue, base layout,
interception, UFOpaedia, help.

Opened from the geoscape screen via single-letter keys. Dialogs use
`+`/`-` for in-modal navigation to avoid the arrow-key priority binding
conflict documented in SKILL.md.
"""

from __future__ import annotations

from typing import Optional

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from . import content
from .engine import Game


class _BaseModal(ModalScreen):
    """Shared framing for our modals."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q",      "dismiss", "Close"),
    ]

    def action_dismiss(self, *args) -> None:
        self.app.pop_screen()


class HelpScreen(_BaseModal):
    def compose(self):
        with Vertical(classes="dialog"):
            yield Static(self._build(), classes="dialog-title")

    def _build(self) -> Text:
        t = Text()
        t.append("OpenXCOM TUI — controls\n\n",
                 style=Style(color="rgb(240,220,140)", bold=True))
        t.append("Geoscape:\n", style="bold")
        t.append("  ← ↑ ↓ →   move globe cursor\n")
        t.append("  space/p   pause\n")
        t.append("  .         advance 1 hour\n")
        t.append("  >         advance 1 day\n")
        t.append("  r         research menu\n")
        t.append("  m         manufacture menu\n")
        t.append("  b         base layout\n")
        t.append("  i         intercept UFO\n")
        t.append("  u         UFOpaedia\n")
        t.append("  g         graphs (funding, score)\n")
        t.append("  h         recenter on base\n")
        t.append("  t         force-start a battle (debug)\n")
        t.append("  q         quit\n\n")
        t.append("Battlescape:\n", style="bold")
        t.append("  ← ↑ ↓ →   move crosshair\n")
        t.append("  w a s d   step selected soldier\n")
        t.append("  tab       cycle soldiers\n")
        t.append("  f         snap shot (25% TU)\n")
        t.append("  F         aimed shot (60% TU)\n")
        t.append("  g         auto burst (35% TU × 3)\n")
        t.append("  e         end player turn\n")
        t.append("  x         abort mission\n\n")
        t.append("Escape closes any modal.", style="dim")
        return t


class ResearchScreen(_BaseModal):
    """Browse available projects, start/cancel. `+`/`-` move cursor,
    Enter starts / cancels the project under cursor."""

    BINDINGS = [
        *_BaseModal.BINDINGS,
        Binding("plus",   "move(1)",  "Down"),
        Binding("minus",  "move(-1)", "Up"),
        Binding("j",      "move(1)",  "Down", show=False),
        Binding("k",      "move(-1)", "Up", show=False),
        Binding("enter",  "toggle",   "Start/Cancel"),
        Binding("]",      "assign(1)",  "More sci"),
        Binding("[",      "assign(-1)", "Less sci"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _entries(self) -> list:
        g: Game = self.app.game
        return content.available_research(g.completed_research)

    def action_move(self, step: int) -> None:
        entries = self._entries()
        if not entries:
            return
        self.cursor = (self.cursor + step) % len(entries)
        self._refresh_body()

    def action_toggle(self) -> None:
        g: Game = self.app.game
        entries = self._entries()
        if not entries:
            return
        r = entries[self.cursor]
        # If in queue, cancel; else start with 2 scientists by default.
        in_queue = any(p.id == r.id for p in g.research_queue)
        if in_queue:
            g.cancel_research(r.id)
        else:
            g.start_research(r.id, assigned=2)
        self._refresh_body()

    def action_assign(self, delta: int) -> None:
        g: Game = self.app.game
        entries = self._entries()
        if not entries:
            return
        r = entries[self.cursor]
        for p in g.research_queue:
            if p.id == r.id:
                p.assigned = max(1, min(p.assigned + delta,
                                        g.bases[0].scientists if g.bases else 99))
                break
        self._refresh_body()

    def _refresh_body(self) -> None:
        g: Game = self.app.game
        t = Text()
        t.append("— RESEARCH —  (Enter start/cancel, +/- select, [/] staff)\n\n",
                 style=Style(color="rgb(240,220,140)", bold=True))
        entries = self._entries()
        if not entries:
            t.append("No projects available. Capture aliens or study alien tech.\n",
                     style="dim")
            self.body.update(t)
            return
        queue_ids = {p.id: p for p in g.research_queue}
        for i, r in enumerate(entries):
            prefix = "▶ " if i == self.cursor else "  "
            is_queued = r.id in queue_ids
            stl = Style(color="rgb(180,220,240)", bold=True) if i == self.cursor \
                  else Style(color="rgb(200,210,230)")
            marker = "[in queue]" if is_queued else ""
            t.append(prefix, style=stl)
            t.append(f"{r.name:<32s}", style=stl)
            t.append(f"  {r.cost}d ", style="dim")
            if is_queued:
                p = queue_ids[r.id]
                pct = int(100 * p.progress / max(1, r.cost * 24))
                t.append(f" ×{p.assigned:2d} ", style=Style(color="rgb(120,220,120)"))
                t.append(f"{pct:3d}% ", style=Style(color="rgb(120,220,120)"))
            t.append(f"{marker}\n", style=Style(color="rgb(220,200,140)"))
        t.append(f"\n{len(entries)} available, {len(g.research_queue)} in queue, "
                 f"{len(g.completed_research)} completed\n", style="dim")
        self.body.update(t)


class ManufactureScreen(_BaseModal):
    """List manufactureable items; Enter starts / cancels."""

    BINDINGS = [
        *_BaseModal.BINDINGS,
        Binding("plus",  "move(1)",  "Down"),
        Binding("minus", "move(-1)", "Up"),
        Binding("j",     "move(1)",  "Down", show=False),
        Binding("k",     "move(-1)", "Up", show=False),
        Binding("enter", "toggle",   "Start/Cancel"),
        Binding("]",     "assign(1)",  "More eng"),
        Binding("[",     "assign(-1)", "Less eng"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _entries(self) -> list:
        g: Game = self.app.game
        return content.manufacturable_items(g.completed_research)

    def action_move(self, step: int) -> None:
        entries = self._entries()
        if not entries:
            return
        self.cursor = (self.cursor + step) % len(entries)
        self._refresh_body()

    def action_toggle(self) -> None:
        g: Game = self.app.game
        entries = self._entries()
        if not entries:
            return
        it = entries[self.cursor]
        in_queue = any(p.id == it.id for p in g.manufacture_queue)
        if in_queue:
            g.cancel_manufacture(it.id)
        else:
            g.start_manufacture(it.id, quantity=5, assigned=5)
        self._refresh_body()

    def action_assign(self, delta: int) -> None:
        g: Game = self.app.game
        entries = self._entries()
        if not entries:
            return
        it = entries[self.cursor]
        for p in g.manufacture_queue:
            if p.id == it.id:
                p.assigned = max(1, min(p.assigned + delta,
                                        g.bases[0].engineers if g.bases else 99))
                break
        self._refresh_body()

    def _refresh_body(self) -> None:
        g: Game = self.app.game
        t = Text()
        t.append("— MANUFACTURE —  (Enter start/cancel ×5, +/- select, [/] staff)\n\n",
                 style=Style(color="rgb(240,220,140)", bold=True))
        entries = self._entries()
        if not entries:
            t.append("Nothing manufactureable yet — complete research first.\n", style="dim")
            self.body.update(t)
            return
        queue_ids = {p.id: p for p in g.manufacture_queue}
        for i, it in enumerate(entries):
            prefix = "▶ " if i == self.cursor else "  "
            stl = Style(color="rgb(180,220,240)", bold=True) if i == self.cursor \
                  else Style(color="rgb(200,210,230)")
            t.append(prefix, style=stl)
            t.append(f"{it.name:<26s}", style=stl)
            t.append(f" {it.build_cost:5d}h  ${it.dollar_cost:>8,}", style="dim")
            if it.id in queue_ids:
                p = queue_ids[it.id]
                t.append(f"  ×{p.assigned} ", style=Style(color="rgb(120,220,120)"))
                t.append(f"{p.produced}/{p.quantity}",
                         style=Style(color="rgb(120,220,120)"))
            t.append("\n")
        self.body.update(t)


class BaseScreen(_BaseModal):
    """Show the 6×6 base interior + facility list."""

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        g: Game = self.app.game
        t = Text()
        t.append("— BASE LAYOUT —\n\n",
                 style=Style(color="rgb(240,220,140)", bold=True))
        if not g.bases:
            t.append("No bases.\n")
            self.body.update(t)
            return
        b = g.bases[0]
        # 6×6 grid — each cell 4 chars wide for readability.
        for y in range(6):
            for x in range(6):
                f = b.facilities.get((x, y))
                if f is None:
                    t.append(" .  ", style="dim")
                else:
                    fac = content.FACILITIES[f.id]
                    stl = (Style(color="rgb(240,200,120)", bold=True)
                           if f.days_left == 0
                           else Style(color="rgb(140,160,200)"))
                    t.append(f" {fac.glyph}  ", style=stl)
            t.append("\n")
        t.append("\nFacilities:\n", style="bold")
        for f in b.facilities.values():
            fac = content.FACILITIES[f.id]
            status = "ready" if f.days_left == 0 else f"{f.days_left}d left"
            t.append(f"  {fac.glyph} {fac.name:<22s}  ${fac.monthly_cost:>6,}/mo  [{status}]\n",
                     style=Style(color="rgb(210,220,240)"))
        t.append(f"\nStaff: {b.scientists} sci  {b.engineers} eng  "
                 f"{len(b.soldier_ids)} soldiers\n", style="dim")
        t.append(f"Lab cap {b.lab_capacity()}  Workshop cap {b.workshop_capacity()}  "
                 f"Living cap {b.living_capacity()}\n", style="dim")
        t.append(f"Radar range {b.radar_range_km()} km  "
                 f"Hangar slots {b.hangar_capacity()}\n", style="dim")
        self.body.update(t)


class InterceptScreen(_BaseModal):
    """List detected UFOs and available craft; allow sending a craft to
    intercept. Instant-resolves the air combat (simplified MVP)."""

    BINDINGS = [
        *_BaseModal.BINDINGS,
        Binding("plus",  "move(1)",  "Down"),
        Binding("minus", "move(-1)", "Up"),
        Binding("j",     "move(1)",  "Down", show=False),
        Binding("k",     "move(-1)", "Up", show=False),
        Binding("enter", "intercept", "Intercept"),
        Binding("l",     "land_at_crash", "Land"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _entries(self) -> list:
        g: Game = self.app.game
        return [u for u in g.ufos.values() if u.detected and not u.shot_down]

    def action_move(self, step: int) -> None:
        entries = self._entries()
        if not entries:
            return
        self.cursor = (self.cursor + step) % len(entries)
        self._refresh_body()

    def action_intercept(self) -> None:
        g: Game = self.app.game
        entries = self._entries()
        if not entries:
            return
        ufo = entries[self.cursor]
        # Find first ready interceptor.
        craft = next((c for c in g.crafts.values()
                      if c.type_id in ("interceptor", "firestorm", "avenger")
                      and c.status == "ready"), None)
        if craft is None:
            g.log_msg("[intercept] no interceptors available")
            self._refresh_body()
            return
        # Resolve instantly — 60% chance for small_scout, drops for big UFOs.
        chance = {"small_scout": 0.7, "medium_scout": 0.6, "large_scout": 0.5,
                  "harvester": 0.45, "abductor": 0.45, "terror_ship": 0.35,
                  "battleship": 0.2}.get(ufo.type_id, 0.5)
        if g.rng.random() < chance:
            ufo.shot_down = True
            g.score += 50
            g.log_msg(f"[intercept] {content.UFO_TYPES[ufo.type_id].name} shot down")
            # Mark crash site alive for a short window — in this MVP, dropping
            # a mission directly on intercept.
        else:
            # Miss — damage the craft.
            craft.damage = min(300, craft.damage + g.rng.randint(20, 60))
            g.log_msg(f"[intercept] {craft.name} missed, -{craft.damage}hp")
        self._refresh_body()

    def action_land_at_crash(self) -> None:
        """Launch a battlescape mission at the first crashed UFO."""
        g: Game = self.app.game
        crashed = [u for u in g.ufos.values() if u.shot_down]
        if not crashed:
            g.log_msg("[intercept] no crash sites")
            return
        g.start_battle(ufo_id=crashed[0].id)
        # Remove the UFO from map (it's now a battle).
        del g.ufos[crashed[0].id]
        self.app.pop_screen()
        self.app.switch_to_battle()

    def _refresh_body(self) -> None:
        g: Game = self.app.game
        t = Text()
        t.append("— INTERCEPTION —  (Enter engage, L land at crash)\n\n",
                 style=Style(color="rgb(240,220,140)", bold=True))
        entries = self._entries()
        if not entries:
            t.append("No UFOs on radar.\n", style="dim")
        else:
            for i, u in enumerate(entries):
                prefix = "▶ " if i == self.cursor else "  "
                stl = (Style(color="rgb(240,180,160)", bold=True) if i == self.cursor
                       else Style(color="rgb(220,200,180)"))
                ut = content.UFO_TYPES[u.type_id]
                t.append(prefix, style=stl)
                t.append(f"{ut.name:<16s}", style=stl)
                t.append(f" @({u.lat:+5.0f},{u.lon:+5.0f})", style="dim")
                t.append(f"  {u.speed_kph} kph  hp {u.hp}  TTL {u.ttl_hours}h\n",
                         style="dim")
        t.append("\nCraft:\n", style="bold")
        for c in g.crafts.values():
            ct = content.CRAFT_TYPES[c.type_id]
            t.append(f"  {c.name:<16s} {ct.name:<12s} fuel {c.fuel}/{ct.max_fuel}  "
                     f"dmg {c.damage}  [{c.status}]\n",
                     style=Style(color="rgb(180,220,240)"))
        crashed = [u for u in g.ufos.values() if u.shot_down]
        if crashed:
            t.append(f"\n{len(crashed)} crash site(s) — press L to land\n",
                     style=Style(color="rgb(120,220,120)", bold=True))
        self.body.update(t)


class GraphsScreen(_BaseModal):
    """Month-end funding + score history as sparkline bars."""

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        g: Game = self.app.game
        t = Text()
        t.append("— HISTORY —\n\n", style=Style(color="rgb(240,220,140)", bold=True))
        t.append("Funding:\n", style="bold")
        t.append(_sparkline(g.history_funds) + "\n",
                 style=Style(color="rgb(120,220,120)"))
        if g.history_funds:
            t.append(f"  latest ${g.history_funds[-1]:,}   "
                     f"min ${min(g.history_funds):,}   "
                     f"max ${max(g.history_funds):,}\n", style="dim")
        t.append("\nScore:\n", style="bold")
        t.append(_sparkline(g.history_score) + "\n",
                 style=Style(color="rgb(240,200,120)"))
        if g.history_score:
            t.append(f"  latest {g.history_score[-1]}   "
                     f"min {min(g.history_score)}   "
                     f"max {max(g.history_score)}\n", style="dim")
        else:
            t.append("  (no data yet — survive a month to see trends)\n",
                     style="dim")
        self.body.update(t)


_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def _sparkline(values: list[int]) -> str:
    if not values:
        return "(no data)"
    vmin = min(values)
    vmax = max(values)
    rng = max(1, vmax - vmin)
    return "".join(_SPARK_CHARS[min(8, int((v - vmin) * 8 / rng))]
                   for v in values[-80:])


class UfopaediaScreen(_BaseModal):
    """Research-gated catalogue."""

    BINDINGS = [
        *_BaseModal.BINDINGS,
        Binding("plus",  "move(1)",  "Down"),
        Binding("minus", "move(-1)", "Up"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def compose(self):
        with Vertical(classes="dialog dialog-wide"):
            self.body = Static("", classes="dialog-title")
            yield self.body

    def on_mount(self) -> None:
        self._refresh_body()

    def _entries(self) -> list:
        g: Game = self.app.game
        out = []
        # Crafts you already own.
        for c in content.CRAFT_TYPES.values():
            out.append(("Craft", c.name,
                        f"speed {c.speed_kph} kph  fuel {c.max_fuel}  "
                        f"cap {c.soldier_capacity}"))
        # Items gated by research.
        for it in content.ITEMS.values():
            if all(r in g.completed_research for r in it.requires):
                out.append(("Item", it.name,
                            f"{it.category}  build {it.build_cost}h  "
                            f"${it.dollar_cost:,}"))
        # Aliens you've studied.
        for rank in content.ALIEN_RANKS.values():
            if rank.research_on_capture and rank.research_on_capture in g.completed_research:
                out.append(("Alien", rank.name,
                            f"HP {rank.hp}  TU {rank.tu}  FA {rank.firing_accuracy}"))
        return out

    def action_move(self, step: int) -> None:
        entries = self._entries()
        if not entries:
            return
        self.cursor = (self.cursor + step) % len(entries)
        self._refresh_body()

    def _refresh_body(self) -> None:
        t = Text()
        t.append("— UFOpaedia —\n\n", style=Style(color="rgb(240,220,140)", bold=True))
        entries = self._entries()
        if not entries:
            t.append("Nothing researched.\n", style="dim")
            self.body.update(t)
            return
        for i, (cat, name, desc) in enumerate(entries):
            prefix = "▶ " if i == self.cursor else "  "
            stl = (Style(color="rgb(240,220,140)", bold=True) if i == self.cursor
                   else Style(color="rgb(200,210,230)"))
            t.append(prefix, style=stl)
            t.append(f"[{cat:<5s}] {name:<22s}", style=stl)
            t.append(f"  {desc}\n", style="dim")
        self.body.update(t)
