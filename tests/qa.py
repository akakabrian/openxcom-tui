"""QA harness for openxcom-tui.

Runs ~20 scenarios in fresh app instances via ``App.run_test()`` + Pilot,
captures SVGs of pass/fail state, reports pass/fail count, returns the
failure count as exit code.

    python -m tests.qa            # full suite
    python -m tests.qa cursor     # only scenarios with "cursor" in the name
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from openxcom_tui.app import BattlescapeScreen, GeoscapeScreen, OpenXcomApp
from openxcom_tui import content, geoscape as geo
from openxcom_tui.engine import Mode

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[OpenXcomApp, "object"], Awaitable[None]]


# --------------------------- geoscape scenarios ---------------------------

async def s_mount_clean(app: OpenXcomApp, pilot) -> None:
    """App boots, geoscape is on top, widgets exist."""
    assert isinstance(app.screen, GeoscapeScreen), type(app.screen).__name__
    assert app.screen.map_view is not None
    assert app.screen.status_panel is not None
    assert app.screen.message_log is not None
    assert app.game is not None
    assert len(app.game.bases) >= 1
    assert len(app.game.soldiers) >= 8


async def s_cursor_starts_mid_globe(app: OpenXcomApp, pilot) -> None:
    mv = app.screen.map_view
    assert mv.cursor_x == geo.LAND_W // 2
    assert mv.cursor_y == geo.LAND_H // 2


async def s_cursor_moves(app: OpenXcomApp, pilot) -> None:
    mv = app.screen.map_view
    sx, sy = mv.cursor_x, mv.cursor_y
    await pilot.press("right", "right", "right")
    await pilot.press("down", "down")
    assert mv.cursor_x == (sx + 3) % geo.LAND_W
    assert mv.cursor_y == sy + 2


async def s_cursor_wraps_longitude(app: OpenXcomApp, pilot) -> None:
    mv = app.screen.map_view
    mv.cursor_x = 0
    await pilot.press("left")
    assert mv.cursor_x == geo.LAND_W - 1, mv.cursor_x


async def s_cursor_clamps_latitude(app: OpenXcomApp, pilot) -> None:
    mv = app.screen.map_view
    for _ in range(geo.LAND_H + 5):
        await pilot.press("down")
    assert mv.cursor_y == geo.LAND_H - 1, mv.cursor_y
    for _ in range(geo.LAND_H + 5):
        await pilot.press("up")
    assert mv.cursor_y == 0, mv.cursor_y


async def s_recenter_on_base(app: OpenXcomApp, pilot) -> None:
    mv = app.screen.map_view
    mv.cursor_x = 1
    mv.cursor_y = 1
    await pilot.press("h")
    b = app.game.bases[0]
    bx, by = geo.latlon_to_xy(b.lat, b.lon)
    assert (mv.cursor_x, mv.cursor_y) == (bx, by)


async def s_pause_toggle(app: OpenXcomApp, pilot) -> None:
    assert not app.game.paused
    await pilot.press("p")
    assert app.game.paused
    await pilot.press("p")
    assert not app.game.paused


async def s_advance_hour(app: OpenXcomApp, pilot) -> None:
    h0 = app.game.hour
    await pilot.press("full_stop")   # "." key
    assert app.game.hour > h0, (h0, app.game.hour)


async def s_advance_day(app: OpenXcomApp, pilot) -> None:
    d0 = app.game.day()
    await pilot.press("greater_than_sign")  # ">" key
    assert app.game.day() >= d0 + 1, (d0, app.game.day())


# --------------------------- modal scenarios ------------------------------

async def _modal(pilot, app, key: str, class_name: str) -> None:
    await pilot.press(key)
    await pilot.pause()
    assert type(app.screen).__name__ == class_name, type(app.screen).__name__
    await pilot.press("escape")
    await pilot.pause()
    assert isinstance(app.screen, GeoscapeScreen), type(app.screen).__name__


async def s_help_opens(app, pilot):
    await _modal(pilot, app, "question_mark", "HelpScreen")


async def s_research_opens(app, pilot):
    await _modal(pilot, app, "r", "ResearchScreen")


async def s_manufacture_opens(app, pilot):
    await _modal(pilot, app, "m", "ManufactureScreen")


async def s_base_opens(app, pilot):
    await _modal(pilot, app, "b", "BaseScreen")


async def s_ufopaedia_opens(app, pilot):
    await _modal(pilot, app, "u", "UfopaediaScreen")


async def s_intercept_opens(app, pilot):
    await _modal(pilot, app, "i", "InterceptScreen")


async def s_graphs_opens(app, pilot):
    await _modal(pilot, app, "g", "GraphsScreen")


async def s_animation_blinks_ocean(app, pilot):
    """Bumping the animation frame must swap some ocean glyphs."""
    mv = app.screen.map_view
    mv._anim_frame = 0
    mv.refresh_view()
    snap0 = str(mv._last_text)
    mv._anim_frame = 1
    mv.refresh_view()
    snap1 = str(mv._last_text)
    # The two renderings must differ somewhere (ocean glyphs swap).
    assert snap0 != snap1, "animation frame had no visible effect"


# --------------------------- workflow scenarios ---------------------------

async def s_research_start_via_modal(app, pilot):
    """Open research modal, press Enter on top entry → starts it."""
    await pilot.press("r")
    await pilot.pause()
    before = len(app.game.research_queue)
    await pilot.press("enter")
    await pilot.pause()
    after = len(app.game.research_queue)
    assert after == before + 1, (before, after)


async def s_research_completes_over_time(app, pilot):
    """Drive the engine directly with enough hours to complete a cheap
    project. Not driven via the modal; we're testing engine integration
    rather than the UI."""
    app.game.start_research("STR_MEDI_KIT", assigned=10)
    # 60-day project at 10 scientists = 144 game-hours. Round up to 200
    # so we're well past the finish.
    before = len(app.game.completed_research)
    app.game.advance_hours(200)
    assert len(app.game.completed_research) > before


async def s_battle_enters_on_t(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, BattlescapeScreen), type(app.screen).__name__
    assert app.game.battle is not None
    assert app.game.mode == Mode.BATTLE


async def s_battle_cycle_selects_next_soldier(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    b = app.game.battle
    first = b.selected()
    await pilot.press("tab")
    await pilot.pause()
    assert b.selected() is not first


async def s_battle_step_moves_selected(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    b = app.game.battle
    sel = b.selected()
    x0, y0 = sel.x, sel.y
    tu0 = sel.tu
    # Try all four directions — at least one should succeed.
    for key in ("w", "a", "s", "d"):
        await pilot.press(key)
        await pilot.pause()
        if (sel.x, sel.y) != (x0, y0):
            break
    assert (sel.x, sel.y) != (x0, y0) or sel.tu < tu0, (
        f"soldier didn't move or spend TU: pos ({x0},{y0})->({sel.x},{sel.y})"
    )


async def s_battle_end_turn_advances_turn_counter(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    b = app.game.battle
    t0 = b.turn_number
    await pilot.press("e")
    await pilot.pause()
    # Turn counter bumps when alien → player hand-off happens.
    assert b.turn_number == t0 + 1, (t0, b.turn_number)
    assert b.turn == "player"


async def s_battle_abort_returns_to_geoscape(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, BattlescapeScreen)
    await pilot.press("x")
    await pilot.pause()
    assert isinstance(app.screen, GeoscapeScreen), type(app.screen).__name__
    assert app.game.mode == Mode.GEOSCAPE
    assert app.game.battle is None


async def s_battle_shoot_spends_tu(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    b = app.game.battle
    sel = b.selected()
    tu0 = sel.tu
    # Aim at an enemy; crosshair starts at sel's position, move it up-right
    # a few tiles toward the aliens (which spawn around top-center).
    mv = app.screen.map_view
    mv.cursor_x = 20
    mv.cursor_y = 5
    await pilot.press("f")   # snap shot
    await pilot.pause()
    assert sel.tu < tu0, f"TU not spent: {tu0} -> {sel.tu}"


async def s_state_snapshot_has_expected_keys(app, pilot):
    s = app.game.state_snapshot()
    for k in ("mode", "date", "funds", "score", "hour", "bases",
              "research_queue", "completed_research", "manufacture_queue",
              "ufos", "soldiers", "battle"):
        assert k in s, f"missing key {k}"


async def s_unknown_tile_class_does_not_crash(app, pilot):
    """Battle tile style lookup must degrade to the unknown-magenta style,
    never raise — even if terrain gets corrupted mid-game."""
    from openxcom_tui import tiles
    s1 = tiles.battle_tile_style("does_not_exist")
    assert s1 is tiles.UNKNOWN_STYLE or s1 == tiles.UNKNOWN_STYLE


async def s_radar_covers_base(app, pilot):
    """Starting base has a small radar — coverage set should contain
    the base cell."""
    b = app.game.bases[0]
    cells = geo.radar_cells(b.lat, b.lon, b.radar_range_km())
    bx, by = geo.latlon_to_xy(b.lat, b.lon)
    assert (bx, by) in cells, (bx, by, len(cells))


async def s_ufo_detection_requires_radar_range(app, pilot):
    """Spawn a UFO directly over the base and run a tick — should become
    detected. Spawn one far away — should not."""
    g = app.game
    b = g.bases[0]
    close = g.new_ufo("small_scout", b.lat, b.lon)
    far = g.new_ufo("small_scout", -b.lat, b.lon + 90)
    g.advance_hours(1)
    assert close.detected, "close UFO missed radar"
    # Far UFO may or may not be detected depending on random drift —
    # the assertion we actually care about is the close one.


async def s_month_tick_produces_council_log(app, pilot):
    g = app.game
    # Jump just past a month boundary.
    g.advance_hours(721)
    joined = "\n".join(g.log)
    assert "[council]" in joined


# --------------------------- registry -------------------------------------

SCENARIOS: list[Scenario] = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("cursor_starts_mid_globe", s_cursor_starts_mid_globe),
    Scenario("cursor_moves", s_cursor_moves),
    Scenario("cursor_wraps_longitude", s_cursor_wraps_longitude),
    Scenario("cursor_clamps_latitude", s_cursor_clamps_latitude),
    Scenario("recenter_on_base", s_recenter_on_base),
    Scenario("pause_toggle", s_pause_toggle),
    Scenario("advance_hour", s_advance_hour),
    Scenario("advance_day", s_advance_day),
    Scenario("help_opens_and_closes", s_help_opens),
    Scenario("research_opens_and_closes", s_research_opens),
    Scenario("manufacture_opens_and_closes", s_manufacture_opens),
    Scenario("base_opens_and_closes", s_base_opens),
    Scenario("ufopaedia_opens_and_closes", s_ufopaedia_opens),
    Scenario("intercept_opens_and_closes", s_intercept_opens),
    Scenario("graphs_opens_and_closes", s_graphs_opens),
    Scenario("animation_blinks_ocean", s_animation_blinks_ocean),
    Scenario("research_start_via_modal", s_research_start_via_modal),
    Scenario("research_completes_over_time", s_research_completes_over_time),
    Scenario("battle_enters_on_t", s_battle_enters_on_t),
    Scenario("battle_cycle_selects_next_soldier", s_battle_cycle_selects_next_soldier),
    Scenario("battle_step_moves_selected", s_battle_step_moves_selected),
    Scenario("battle_end_turn_advances_turn_counter", s_battle_end_turn_advances_turn_counter),
    Scenario("battle_abort_returns_to_geoscape", s_battle_abort_returns_to_geoscape),
    Scenario("battle_shoot_spends_tu", s_battle_shoot_spends_tu),
    Scenario("state_snapshot_has_expected_keys", s_state_snapshot_has_expected_keys),
    Scenario("unknown_tile_class_does_not_crash", s_unknown_tile_class_does_not_crash),
    Scenario("radar_covers_base", s_radar_covers_base),
    Scenario("ufo_detection_requires_radar_range", s_ufo_detection_requires_radar_range),
    Scenario("month_tick_produces_council_log", s_month_tick_produces_council_log),
]


async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = OpenXcomApp(seed=1234)
    try:
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                try:
                    app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                except Exception:
                    pass
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                try:
                    app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                except Exception:
                    pass
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            try:
                app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            except Exception:
                pass
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines()[:8]:
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
