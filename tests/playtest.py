"""End-to-end scripted playtest.

Drives a real Textual app through a scripted scenario via the Pilot:
  1. Boot geoscape.
  2. Advance one game-day (`>`).
  3. Open the research modal (`r`), queue the top project, close it.
  4. Open the base view (`b`), close it.
  5. Open the UFOpaedia (`u`), close it.
  6. Quit (`q`).

Captures an SVG snapshot at each checkpoint under ``tests/out/``. This is
the integration-test equivalent of a pexpect-driven PTY dialogue, but
runs in-process so we can assert on app state too.

    python -m tests.playtest
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import cast

from openxcom_tui.app import BattlescapeScreen, GeoscapeScreen, OpenXcomApp
from openxcom_tui.engine import Mode

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


async def playtest() -> int:
    app = OpenXcomApp(seed=4242)
    steps: list[tuple[str, bool, str]] = []

    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause()

        # 1. Boot geoscape
        ok = isinstance(app.screen, GeoscapeScreen)
        app.save_screenshot(str(OUT / "playtest_01_boot_geoscape.svg"))
        steps.append(("boot_geoscape", ok,
                      "" if ok else f"screen is {type(app.screen).__name__}"))

        # 2. Advance one game-day via ">"
        d0 = app.game.day()
        await pilot.press("greater_than_sign")
        await pilot.pause()
        ok = app.game.day() >= d0 + 1
        app.save_screenshot(str(OUT / "playtest_02_advance_day.svg"))
        steps.append(("advance_day", ok, f"day {d0} -> {app.game.day()}"))

        # 3. Open research modal, queue the top project, close
        qlen0 = len(app.game.research_queue)
        await pilot.press("r")
        await pilot.pause()
        ok_open = type(app.screen).__name__ == "ResearchScreen"
        app.save_screenshot(str(OUT / "playtest_03_research_open.svg"))
        await pilot.press("enter")  # start top project
        await pilot.pause()
        qlen1 = len(app.game.research_queue)
        app.save_screenshot(str(OUT / "playtest_04_research_queued.svg"))
        await pilot.press("escape")
        await pilot.pause()
        ok_close = isinstance(app.screen, GeoscapeScreen)
        steps.append(("research_modal", ok_open and ok_close and qlen1 > qlen0,
                      f"open={ok_open} close={ok_close} queue {qlen0}->{qlen1}"))

        # 4. Open base view
        await pilot.press("b")
        await pilot.pause()
        ok_open = type(app.screen).__name__ == "BaseScreen"
        app.save_screenshot(str(OUT / "playtest_05_base_view.svg"))
        await pilot.press("escape")
        await pilot.pause()
        steps.append(("base_view", ok_open and isinstance(app.screen, GeoscapeScreen),
                      f"open={ok_open}"))

        # 5. Open UFOpaedia
        await pilot.press("u")
        await pilot.pause()
        ok_open = type(app.screen).__name__ == "UfopaediaScreen"
        app.save_screenshot(str(OUT / "playtest_06_ufopaedia.svg"))
        await pilot.press("escape")
        await pilot.pause()
        steps.append(("ufopaedia", ok_open and isinstance(app.screen, GeoscapeScreen),
                      f"open={ok_open}"))

        # 6. Enter battle, take one action, save a snapshot, abort
        await pilot.press("t")
        await pilot.pause()
        ok_battle = isinstance(app.screen, BattlescapeScreen)
        app.save_screenshot(str(OUT / "playtest_07_battle.svg"))
        steps.append(("enter_battle", ok_battle,
                      f"mode={app.game.mode.value}"))
        if ok_battle:
            await pilot.press("d")   # step right
            await pilot.pause()
            app.save_screenshot(str(OUT / "playtest_08_battle_step.svg"))
            await pilot.press("x")   # abort
            await pilot.pause()
            ok_back = isinstance(app.screen, GeoscapeScreen)
            steps.append(("battle_abort", ok_back, f"mode={app.game.mode.value}"))

        # 7. Quit
        await pilot.press("q")
        await pilot.pause()

    passed = sum(1 for _, ok, _ in steps if ok)
    total = len(steps)
    for name, ok, msg in steps:
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name:<20s}  {msg}")
    print(f"\n{passed}/{total} steps passed")
    print(f"SVGs saved to {OUT}/playtest_*.svg")
    return 0 if passed == total else 1


def main() -> int:
    return asyncio.run(playtest())


if __name__ == "__main__":
    sys.exit(main())
