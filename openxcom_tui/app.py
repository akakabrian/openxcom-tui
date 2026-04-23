"""Textual App — geoscape + battlescape two-layer TUI.

Structure:
  * ``OpenXcomApp`` owns the ``Game`` instance and the two screens.
  * The default screen is ``GeoscapeScreen`` (globe + base panel + log).
  * When ``game.mode == BATTLE`` the app pushes ``BattlescapeScreen``;
    on ``end_battle`` we pop back to geoscape.
  * Both screens share the same ``game`` reference and tick timer — the
    app drives the clock.

Performance: scaffold version renders via ``Static.update(Text)`` which
is fine for 120×36 (~4k cells, ~50 ms rebuild worst-case). See
tests/perf.py baselines — Stage 5 can switch to ScrollView + render_line
if we exceed 30 ms per frame.
"""

from __future__ import annotations

import asyncio
from typing import Optional, cast

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static

from . import content, tiles
from .engine import Game, new_game
from .battlescape import BATTLE_H, BATTLE_W, Battle
from . import geoscape as geo


# ---- geoscape widgets ----------------------------------------------------

class GeoscapeMapView(Static):
    """Renders the ASCII Mercator globe plus base, UFO, craft markers."""

    def __init__(self, game: Game, **kw):
        super().__init__("", **kw)
        self.game = game
        self.cursor_x = geo.LAND_W // 2
        self.cursor_y = geo.LAND_H // 2
        # 2 Hz animation frame counter — used to swap water/ufo glyphs.
        self._anim_frame = 0
        # Precomputed cell kind cache — globe topology doesn't change.
        self._kind_cache: list[list[str]] | None = None

    def _cell_kind(self, x: int, y: int) -> str:
        ch = geo.land_at(x, y)
        if ch == "#":
            return "land"
        # Simple coastal detection: ocean cell adjacent to land.
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if geo.land_at(x + dx, y + dy) == "#":
                    return "coast"
        return "ocean"

    def _build_kind_cache(self) -> list[list[str]]:
        """Precompute land/coast/ocean classification for every cell —
        land topology is static so we can cache it forever."""
        cache: list[list[str]] = []
        for y in range(geo.LAND_H):
            row: list[str] = []
            for x in range(geo.LAND_W):
                row.append(self._cell_kind(x, y))
            cache.append(row)
        return cache

    def refresh_view(self) -> None:
        # Build the rich Text for the whole globe. At 120×36 this runs
        # comfortably under the 1 Hz refresh interval.
        text = Text()
        if self._kind_cache is None:
            self._kind_cache = self._build_kind_cache()
        kinds = self._kind_cache
        # Precompute marker overrides: base, UFOs, craft, cursor.
        overrides: dict[tuple[int, int], tuple[str, Style]] = {}
        # Radar coverage.
        radar_cells: set[tuple[int, int]] = set()
        for b in self.game.bases:
            rng = b.radar_range_km()
            if rng > 0:
                radar_cells |= geo.radar_cells(b.lat, b.lon, rng)
        # Bases.
        for b in self.game.bases:
            bx, by = geo.latlon_to_xy(b.lat, b.lon)
            overrides[(bx, by)] = ("X", tiles.STYLE_BASE)
        # Country markers (light).
        for name, (lat, lon) in content.COUNTRY_CENTRES.items():
            cx, cy = geo.latlon_to_xy(lat, lon)
            overrides.setdefault((cx, cy), ("⌂", tiles.STYLE_CITY))
        # UFOs — only render if detected (gives radar coverage meaning).
        # Animate via 2 Hz glyph swap so the eye is drawn to the blip.
        blink = self._anim_frame & 1
        for u in self.game.ufos.values():
            if u.shot_down:
                continue
            if not u.detected:
                continue
            ux, uy = geo.latlon_to_xy(u.lat, u.lon)
            ut = content.UFO_TYPES[u.type_id]
            glyph = ut.glyph if blink else "*"
            overrides[(ux, uy)] = (glyph, tiles.STYLE_UFO)
        # Craft in flight.
        for c in self.game.crafts.values():
            if c.lat is None or c.lon is None:
                continue
            cx, cy = geo.latlon_to_xy(c.lat, c.lon)
            overrides[(cx, cy)] = ("✈", tiles.STYLE_CRAFT)

        cursor = (self.cursor_x, self.cursor_y)
        for y in range(geo.LAND_H):
            row_kinds = kinds[y]
            for x in range(geo.LAND_W):
                if (x, y) in overrides:
                    gch, st = overrides[(x, y)]
                    if (x, y) == cursor:
                        st = tiles.STYLE_CURSOR
                    text.append(gch, style=st)
                    continue
                kind = row_kinds[x]
                st = tiles.geo_cell_style(kind)
                if (x, y) in radar_cells and kind == "ocean":
                    st = tiles.STYLE_RADAR
                gch = tiles.geo_cell_glyph(kind, x, y)
                # Animate ocean with 2-glyph swap every other frame.
                if kind == "ocean" and blink:
                    gch = "~" if gch == "≈" else "≈"
                if (x, y) == cursor:
                    st = tiles.STYLE_CURSOR
                text.append(gch, style=st)
            text.append("\n")
        self._last_text = text
        self.update(text)

    # --- input

    def move_cursor(self, dx: int, dy: int) -> None:
        self.cursor_x = (self.cursor_x + dx) % geo.LAND_W
        self.cursor_y = max(0, min(geo.LAND_H - 1, self.cursor_y + dy))
        self.refresh_view()

    def cell_lat_lon(self) -> tuple[float, float]:
        return geo.xy_to_latlon(self.cursor_x, self.cursor_y)


class SidePanel(Static):
    """Right-hand status panel — funds, date, research/manufacture summary."""

    def __init__(self, game: Game, **kw):
        super().__init__("", **kw)
        self.game = game

    def refresh_panel(self) -> None:
        g = self.game
        t = Text()
        t.append("— X-COM STATUS —\n", style=Style(color="rgb(240,220,140)", bold=True))
        t.append(f"{g.date_str()}\n", style=Style(color="rgb(180,200,220)"))
        t.append(f"Funds : ", style="dim")
        fund_col = "rgb(120,220,120)" if g.funds >= 0 else "rgb(240,90,90)"
        t.append(f"${g.funds:,}\n", style=Style(color=fund_col, bold=True))
        t.append(f"Score : {g.score}\n", style="dim")
        t.append("\n")
        if g.bases:
            b = g.bases[0]
            t.append(f"Base {b.name}\n", style=Style(color="rgb(220,200,140)", bold=True))
            t.append(f"  Scientists: {b.scientists}\n", style="dim")
            t.append(f"  Engineers : {b.engineers}\n", style="dim")
            t.append(f"  Soldiers  : {len(b.soldier_ids)}\n", style="dim")
            t.append(f"  Lab cap   : {b.lab_capacity()}\n", style="dim")
            t.append(f"  Shop cap  : {b.workshop_capacity()}\n", style="dim")
            t.append(f"  Radar km  : {b.radar_range_km()}\n", style="dim")
        t.append("\nResearch:\n", style=Style(color="rgb(200,220,240)", bold=True))
        if not g.research_queue:
            t.append("  (idle)\n", style="dim")
        else:
            for p in g.research_queue[:3]:
                r = content.RESEARCH[p.id]
                pct = int(100 * p.progress / max(1, r.cost * 24))
                t.append(f"  {r.name[:22]:22s} {pct:3d}%\n",
                         style=Style(color="rgb(180,220,240)"))
        t.append("\nMfg:\n", style=Style(color="rgb(200,220,240)", bold=True))
        if not g.manufacture_queue:
            t.append("  (idle)\n", style="dim")
        else:
            for p in g.manufacture_queue[:3]:
                it = content.ITEMS[p.id]
                t.append(f"  {it.name[:22]:22s} {p.produced}/{p.quantity}\n",
                         style=Style(color="rgb(220,200,140)"))
        t.append("\nDetected UFOs:\n", style=Style(color="rgb(240,120,120)", bold=True))
        det = [u for u in g.ufos.values() if u.detected and not u.shot_down]
        if not det:
            t.append("  (none)\n", style="dim")
        else:
            for u in det[:4]:
                ut = content.UFO_TYPES[u.type_id]
                t.append(f"  {ut.name} @({u.lat:+.0f},{u.lon:+.0f})\n",
                         style=Style(color="rgb(240,160,160)"))
        self.update(t)


class GeoscapeScreen(Screen):
    """Primary screen: globe + status + log."""

    BINDINGS = [
        Binding("up",    "move(0,-1)",  priority=True, show=False),
        Binding("down",  "move(0,1)",   priority=True, show=False),
        Binding("left",  "move(-1,0)",  priority=True, show=False),
        Binding("right", "move(1,0)",   priority=True, show=False),
        Binding("space", "toggle_pause", "Pause"),
        Binding("p",     "toggle_pause", "Pause"),
        Binding("r",     "open_research", "Research"),
        Binding("m",     "open_manufacture", "Manufacture"),
        Binding("b",     "open_base", "Base"),
        Binding("i",     "open_intercept", "Intercept"),
        Binding("u",     "open_ufopaedia", "UFOpaedia"),
        Binding("g",     "open_graphs", "Graphs"),
        Binding("h",     "recenter", "Home"),
        Binding("question_mark", "open_help", "Help"),
        Binding(">",     "advance_day", "Day+"),
        Binding(".",     "advance_hour", "Hr+"),
        Binding("t",     "start_battle", "Battle"),
        Binding("q",     "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.map_view: Optional[GeoscapeMapView] = None
        self.status_panel: Optional[SidePanel] = None
        self.flash_bar: Optional[Static] = None
        self.message_log: Optional[RichLog] = None
        self._flash_timer = None

    @property
    def oxc_app(self) -> "OpenXcomApp":
        return cast("OpenXcomApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left-col"):
                self.map_view = GeoscapeMapView(self.oxc_app.game, id="map")
                yield self.map_view
                self.flash_bar = Static("", id="flash-bar")
                yield self.flash_bar
                self.message_log = RichLog(id="log-panel", max_lines=500,
                                            highlight=False, markup=True)
                yield self.message_log
            with Vertical(id="right-col"):
                self.status_panel = SidePanel(self.oxc_app.game, id="status-panel")
                yield self.status_panel
        yield Footer()

    def on_mount(self) -> None:
        assert self.map_view and self.status_panel
        self.map_view.refresh_view()
        self.status_panel.refresh_panel()
        self._pipe_log()

    def _pipe_log(self) -> None:
        """Copy pending engine log messages into the widget."""
        if self.message_log is None:
            return
        game: Game = self.oxc_app.game
        # Only write new entries since last call — track length.
        already = getattr(self, "_log_consumed", 0)
        for msg in game.log[already:]:
            self.message_log.write(msg)
        self._log_consumed = len(game.log)

    def flash(self, msg: str, seconds: float = 2.0) -> None:
        if self.flash_bar is None:
            return
        self.flash_bar.update(msg)
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(seconds, self._clear_flash)

    def _clear_flash(self) -> None:
        if self.flash_bar is not None:
            self.flash_bar.update("")

    # --- actions

    def action_move(self, dx: int, dy: int) -> None:
        if self.map_view:
            self.map_view.move_cursor(dx, dy)

    def action_recenter(self) -> None:
        if self.map_view is None or not self.oxc_app.game.bases:
            return
        b = self.oxc_app.game.bases[0]
        self.map_view.cursor_x, self.map_view.cursor_y = geo.latlon_to_xy(b.lat, b.lon)
        self.map_view.refresh_view()

    def action_toggle_pause(self) -> None:
        g: Game = self.oxc_app.game
        g.paused = not g.paused
        self.flash("PAUSED" if g.paused else "running")

    def action_advance_day(self) -> None:
        self.oxc_app.game.advance_hours(24)
        self.refresh_all()

    def action_advance_hour(self) -> None:
        self.oxc_app.game.advance_hours(1)
        self.refresh_all()

    def action_start_battle(self) -> None:
        """Debug / player-initiated: drop into a battle with no UFO context."""
        self.oxc_app.game.start_battle()
        self.oxc_app.switch_to_battle()

    def action_open_research(self) -> None:
        from .screens import ResearchScreen
        self.app.push_screen(ResearchScreen())

    def action_open_manufacture(self) -> None:
        from .screens import ManufactureScreen
        self.app.push_screen(ManufactureScreen())

    def action_open_base(self) -> None:
        from .screens import BaseScreen
        self.app.push_screen(BaseScreen())

    def action_open_intercept(self) -> None:
        from .screens import InterceptScreen
        self.app.push_screen(InterceptScreen())

    def action_open_ufopaedia(self) -> None:
        from .screens import UfopaediaScreen
        self.app.push_screen(UfopaediaScreen())

    def action_open_graphs(self) -> None:
        from .screens import GraphsScreen
        self.app.push_screen(GraphsScreen())

    def action_open_help(self) -> None:
        from .screens import HelpScreen
        self.app.push_screen(HelpScreen())

    # --- refresh

    def refresh_all(self) -> None:
        if self.map_view:
            self.map_view.refresh_view()
        if self.status_panel:
            self.status_panel.refresh_panel()
        self._pipe_log()


# ---- battlescape widgets -------------------------------------------------

class BattleMapView(Static):
    """Renders the tactical grid + units + cursor."""

    def __init__(self, game: Game, **kw):
        super().__init__("", **kw)
        self.game = game
        self.cursor_x = BATTLE_W // 2
        self.cursor_y = BATTLE_H // 2

    def refresh_view(self) -> None:
        battle: Optional[Battle] = self.game.battle
        if battle is None:
            self.update("(no battle)")
            return
        text = Text()
        sel = battle.selected()
        unit_at = {(u.x, u.y): u for u in battle.units if u.alive}
        for y in range(BATTLE_H):
            for x in range(BATTLE_W):
                if (x, y) == (self.cursor_x, self.cursor_y):
                    # Draw cursor; under it either unit or tile.
                    u = unit_at.get((x, y))
                    if u:
                        text.append(u.glyph, style=tiles.CURSOR_STYLE)
                    else:
                        klass = battle.tile(x, y)
                        text.append(tiles.battle_tile_glyph(klass, x, y),
                                    style=tiles.CURSOR_STYLE)
                    continue
                u = unit_at.get((x, y))
                if u:
                    if sel and u is sel:
                        st = tiles.UNIT_STYLE_SELECTED
                    elif u.side == "player":
                        st = tiles.UNIT_STYLE_PLAYER
                    else:
                        st = tiles.UNIT_STYLE_ALIEN
                    text.append(u.glyph, style=st)
                    continue
                klass = battle.tile(x, y)
                text.append(tiles.battle_tile_glyph(klass, x, y),
                            style=tiles.battle_tile_style(klass))
            text.append("\n")
        self.update(text)

    def move_cursor(self, dx: int, dy: int) -> None:
        self.cursor_x = max(0, min(BATTLE_W - 1, self.cursor_x + dx))
        self.cursor_y = max(0, min(BATTLE_H - 1, self.cursor_y + dy))
        self.refresh_view()


class BattleSidePanel(Static):
    def __init__(self, game: Game, **kw):
        super().__init__("", **kw)
        self.game = game

    def refresh_panel(self) -> None:
        battle: Optional[Battle] = self.game.battle
        if battle is None:
            self.update("")
            return
        t = Text()
        t.append("— BATTLESCAPE —\n",
                 style=Style(color="rgb(240,140,140)", bold=True))
        t.append(f"Turn {battle.turn_number}  [{battle.turn}]\n", style="dim")
        t.append(f"Players alive: {len(battle.player_units())}\n",
                 style=Style(color="rgb(120,220,255)"))
        t.append(f"Aliens alive : {len(battle.alien_units())}\n",
                 style=Style(color="rgb(255,120,120)"))
        t.append("\n")
        sel = battle.selected()
        if sel:
            t.append("Selected:\n", style=Style(color="rgb(240,220,140)", bold=True))
            t.append(f"  {sel.name}\n", style="bold")
            t.append(f"  HP : {sel.hp}/{sel.max_hp}\n", style="dim")
            t.append(f"  TU : {sel.tu}/{sel.max_tu}\n", style="dim")
            t.append(f"  FA : {sel.firing_accuracy}\n", style="dim")
            t.append(f"  XY : ({sel.x},{sel.y})\n", style="dim")
            t.append(f"  Kills (mission): {sel.kills_this_mission}\n", style="dim")
        t.append("\n[Tab] cycle unit\n", style="dim")
        t.append("[hjkl/arrows] move cursor\n", style="dim")
        t.append("[WASD] step selected\n", style="dim")
        t.append("[f] snap / [F] aimed\n", style="dim")
        t.append("[e] end turn\n", style="dim")
        t.append("[x] abort mission\n", style="dim")
        self.update(t)


class BattlescapeScreen(Screen):

    BINDINGS = [
        # Cursor movement (map crosshair).
        Binding("up",    "cursor(0,-1)", priority=True, show=False),
        Binding("down",  "cursor(0,1)",  priority=True, show=False),
        Binding("left",  "cursor(-1,0)", priority=True, show=False),
        Binding("right", "cursor(1,0)",  priority=True, show=False),
        # Step the selected unit with WASD (one-tile move).
        Binding("w",     "step(0,-1)",   "Step↑"),
        Binding("s",     "step(0,1)",    "Step↓"),
        Binding("a",     "step(-1,0)",   "Step←"),
        Binding("d",     "step(1,0)",    "Step→"),
        Binding("tab",   "next_unit",    "Cycle"),
        Binding("f",     "shoot('snap')",  "Snap"),
        Binding("F",     "shoot('aimed')", "Aim"),
        Binding("g",     "shoot('auto')",  "Auto"),
        Binding("e",     "end_turn",     "End"),
        Binding("x",     "abort",        "Abort"),
        Binding("question_mark", "open_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.map_view: Optional[BattleMapView] = None
        self.status_panel: Optional[BattleSidePanel] = None
        self.message_log: Optional[RichLog] = None

    @property
    def oxc_app(self) -> "OpenXcomApp":
        return cast("OpenXcomApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left-col"):
                self.map_view = BattleMapView(self.oxc_app.game, id="map")
                yield self.map_view
                self.message_log = RichLog(id="log-panel", max_lines=200,
                                            highlight=False, markup=True)
                yield self.message_log
            with Vertical(id="right-col"):
                self.status_panel = BattleSidePanel(self.oxc_app.game, id="status-panel")
                yield self.status_panel
        yield Footer()

    def on_mount(self) -> None:
        # Center cursor on selected unit.
        battle = self.oxc_app.game.battle
        if battle is not None:
            sel = battle.selected()
            if sel and self.map_view:
                self.map_view.cursor_x = sel.x
                self.map_view.cursor_y = sel.y
        self.refresh_all()

    # --- actions

    def action_cursor(self, dx: int, dy: int) -> None:
        if self.map_view:
            self.map_view.move_cursor(dx, dy)

    def action_next_unit(self) -> None:
        battle = self.oxc_app.game.battle
        if battle is None:
            return
        battle.cycle_selection(1)
        sel = battle.selected()
        if sel and self.map_view:
            self.map_view.cursor_x = sel.x
            self.map_view.cursor_y = sel.y
        self.refresh_all()

    def action_step(self, dx: int, dy: int) -> None:
        battle = self.oxc_app.game.battle
        if battle is None:
            return
        r = battle.move_selected(dx, dy)
        sel = battle.selected()
        if sel and self.map_view:
            self.map_view.cursor_x = sel.x
            self.map_view.cursor_y = sel.y
        if self.message_log:
            self.message_log.write(f"[move] {r}")
        self.refresh_all()
        self._check_outcome()

    def action_shoot(self, mode: str = "snap") -> None:
        battle = self.oxc_app.game.battle
        if battle is None or self.map_view is None:
            return
        tx, ty = self.map_view.cursor_x, self.map_view.cursor_y
        r = battle.shoot_selected(tx, ty, mode=mode)
        if self.message_log:
            self.message_log.write(f"[{mode}] {r}")
        self.refresh_all()
        self._check_outcome()

    def action_end_turn(self) -> None:
        battle = self.oxc_app.game.battle
        if battle is None:
            return
        events = battle.end_player_turn()
        if self.message_log:
            for ev in events:
                self.message_log.write(ev)
            self.message_log.write(f"[turn] {battle.turn_number} begins")
        self.refresh_all()
        self._check_outcome()

    def action_abort(self) -> None:
        self.oxc_app.game.end_battle(victory=False)
        self.oxc_app.switch_to_geoscape()

    def action_open_help(self) -> None:
        from .screens import HelpScreen
        self.app.push_screen(HelpScreen())

    # --- helpers

    def refresh_all(self) -> None:
        if self.map_view:
            self.map_view.refresh_view()
        if self.status_panel:
            self.status_panel.refresh_panel()

    def _check_outcome(self) -> None:
        battle = self.oxc_app.game.battle
        if battle is None:
            return
        out = battle.outcome()
        if out is None:
            return
        victory = (out == "victory")
        # Pull alien captives out of surviving stunned aliens. None in MVP,
        # but tag any alien left alive whose HP <= 15% as "captured".
        for a in battle.alien_units():
            if a.hp <= a.max_hp * 0.15:
                battle.captives[a.rank_id] = battle.captives.get(a.rank_id, 0) + 1
        self.oxc_app.game.end_battle(victory=victory)
        self.oxc_app.switch_to_geoscape()


# ---- top-level app -------------------------------------------------------

class OpenXcomApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "OpenXCOM TUI"
    SUB_TITLE = "two-layer tactical"

    def __init__(self, *, seed: Optional[int] = None, sound: bool = False,
                 agent_port: Optional[int] = None, headless: bool = False,
                 start_battle: bool = False):
        super().__init__()
        self.game: Game = new_game(seed=seed)
        self._sound_enabled = sound
        self._agent_port = agent_port
        self._headless = headless
        self._start_battle = start_battle
        self._tick_task: Optional[asyncio.Task] = None
        self._agent_runner = None

    # --- mode transitions

    def switch_to_battle(self) -> None:
        # Clear any existing stack, push battle.
        self.push_screen(BattlescapeScreen())

    def switch_to_geoscape(self) -> None:
        # Pop the battle screen.
        self.pop_screen()

    # --- boot

    def on_mount(self) -> None:
        self.push_screen(GeoscapeScreen())
        # Game-time tick: 5 minutes of game time per real second → 1 hour
        # per 12 seconds unpaused. We tick at 2 Hz, advancing 6 game minutes
        # per tick → 1 hour per 10 ticks ≈ 5s. Fast enough to see things
        # move, slow enough to read the log.
        self.set_interval(0.5, self._tick)
        # Periodic screen refresh (1 Hz) — cheaper than refreshing every tick.
        self.set_interval(1.0, self._refresh_screen)
        if self._start_battle:
            # Kick a mission on boot.
            self.call_later(lambda: (self.game.start_battle(), self.switch_to_battle()))
        if self._agent_port is not None:
            # Start REST server as a background task.
            from .agent_api import start_agent_api
            self._agent_runner = start_agent_api(self, self._agent_port)

    def _tick(self) -> None:
        # Each 2 Hz tick = ~3 game minutes. Accumulate and advance when we
        # hit a full hour so the tick lands cleanly on integer hours.
        # Simpler: advance 1 hour per 3 ticks (~1.5 s real time).
        self._tick_accum = getattr(self, "_tick_accum", 0) + 1
        if self._tick_accum >= 3:
            self._tick_accum = 0
            self.game.advance_hours(1)

    def _refresh_screen(self) -> None:
        scn = self.screen
        # Only the top-of-stack screen needs refreshing; deeper screens
        # aren't visible.
        if isinstance(scn, GeoscapeScreen):
            # Bump animation frame (2 Hz blink).
            if scn.map_view is not None:
                scn.map_view._anim_frame ^= 1
            scn.refresh_all()
        elif isinstance(scn, BattlescapeScreen):
            scn.refresh_all()

    async def on_unmount(self) -> None:
        if self._agent_runner is not None:
            await self._agent_runner.cleanup()


def run(seed: Optional[int] = None, *, sound: bool = False,
        agent_port: Optional[int] = None, headless: bool = False,
        start_battle: bool = False) -> None:
    if headless:
        # Run just the game loop + agent API, no Textual.
        import time
        from .agent_api import start_agent_api_standalone
        game = new_game(seed=seed)
        if start_battle:
            game.start_battle()
        port = agent_port or 8888
        print(f"openxcom-tui headless — agent API on port {port}")
        runner = start_agent_api_standalone(game, port)
        try:
            while True:
                time.sleep(1.5)
                game.advance_hours(1)
        except KeyboardInterrupt:
            print("shutdown")
        finally:
            asyncio.run(runner.cleanup())
        return
    app = OpenXcomApp(seed=seed, sound=sound, agent_port=agent_port,
                      headless=False, start_battle=start_battle)
    app.run()
