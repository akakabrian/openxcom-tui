"""Hot-path benchmarks — run before + after optimizations.

    python -m tests.perf

No assertions, just timings. Use the numbers to decide what to optimize.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

from openxcom_tui.app import BattlescapeScreen, GeoscapeScreen, OpenXcomApp
from openxcom_tui.engine import new_game


def _fmt(dt: float) -> str:
    if dt >= 1.0:
        return f"{dt:6.3f} s"
    if dt >= 0.001:
        return f"{dt * 1000:6.3f} ms"
    return f"{dt * 1_000_000:6.1f} µs"


def bench(name: str, fn, iters: int = 1) -> None:
    # Warm-up.
    fn()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    dt = (time.perf_counter() - t0) / iters
    print(f"  {name:<42s} {_fmt(dt)}  ({iters}×)")


def bench_engine() -> None:
    print("--- engine ---")
    g = new_game(seed=7)

    def tick_hour():
        g.advance_hours(1)
    bench("advance_hours(1)", tick_hour, iters=500)

    def snapshot():
        g.state_snapshot()
    bench("state_snapshot", snapshot, iters=500)

    # Battle hot paths
    b = g.start_battle()

    def los():
        b.line_of_sight(0, 0, 39, 39)
    bench("line_of_sight 40×40 diagonal", los, iters=2000)

    def shoot():
        b.shoot_selected(20, 5, "snap")
    bench("shoot_selected", shoot, iters=200)

    g.end_battle(victory=True)


async def bench_ui() -> None:
    print("--- ui ---")
    app = OpenXcomApp(seed=7)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause()
        mv = cast(GeoscapeScreen, app.screen).map_view
        assert mv is not None
        t0 = time.perf_counter()
        for _ in range(50):
            mv.refresh_view()
        dt = (time.perf_counter() - t0) / 50
        print(f"  {'geoscape refresh_view':<42s} {_fmt(dt)}  (50×)")

        # Switch to battle
        await pilot.press("t")
        await pilot.pause()
        bmv = cast(BattlescapeScreen, app.screen).map_view
        assert bmv is not None
        t0 = time.perf_counter()
        for _ in range(50):
            bmv.refresh_view()
        dt = (time.perf_counter() - t0) / 50
        print(f"  {'battle refresh_view':<42s} {_fmt(dt)}  (50×)")


def main() -> None:
    bench_engine()
    asyncio.run(bench_ui())


if __name__ == "__main__":
    main()
