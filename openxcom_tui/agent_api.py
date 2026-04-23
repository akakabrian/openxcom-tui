"""Agent REST API — ``--agent`` or ``--headless`` mode.

Routes:
  GET  /state                         → full snapshot (game + battle)
  POST /advance                       → {"hours": N} (default 1)
  GET  /research                      → list available + in-queue
  POST /research/<id>                 → start {"scientists": N}
  DELETE /research/<id>               → cancel
  GET  /manufacture                   → list manufactureable + queue
  POST /manufacture/<id>              → {"quantity": N, "engineers": M}
  DELETE /manufacture/<id>            → cancel
  POST /battle/start                  → {"ufo_id": optional}
  POST /battle/move                   → {"dx": int, "dy": int}
  POST /battle/shoot                  → {"tx": int, "ty": int, "mode": "snap"}
  POST /battle/end_turn
  POST /battle/abort
  GET  /log?since=N                   → last N log entries (default 20)
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from . import content
from .engine import Game


def _json(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _err(msg: str, status: int = 400) -> web.Response:
    return _json({"error": msg}, status=status)


def _routes(app: web.Application, game_getter) -> None:
    async def state(_):
        return _json(game_getter().state_snapshot())

    async def advance(req):
        body = await _safe_json(req)
        hours = int(body.get("hours", 1))
        events = game_getter().advance_hours(hours)
        return _json({"ok": True, "advanced_hours": hours, "events": events})

    async def research_list(_):
        g = game_getter()
        available = content.available_research(g.completed_research)
        return _json({
            "available": [
                {"id": r.id, "name": r.name, "cost_days": r.cost,
                 "prerequisites": list(r.prerequisites)}
                for r in available
            ],
            "in_queue": [
                {"id": p.id, "progress": p.progress, "assigned": p.assigned}
                for p in g.research_queue
            ],
            "completed": sorted(g.completed_research),
        })

    async def research_start(req):
        rid = req.match_info["rid"]
        body = await _safe_json(req)
        assigned = int(body.get("scientists", 2))
        ok = game_getter().start_research(rid, assigned=assigned)
        return _json({"ok": ok})

    async def research_cancel(req):
        rid = req.match_info["rid"]
        ok = game_getter().cancel_research(rid)
        return _json({"ok": ok})

    async def mfg_list(_):
        g = game_getter()
        items = content.manufacturable_items(g.completed_research)
        return _json({
            "available": [
                {"id": it.id, "name": it.name, "build_hours": it.build_cost,
                 "dollar_cost": it.dollar_cost}
                for it in items
            ],
            "in_queue": [
                {"id": p.id, "quantity": p.quantity, "produced": p.produced,
                 "assigned": p.assigned}
                for p in g.manufacture_queue
            ],
        })

    async def mfg_start(req):
        iid = req.match_info["iid"]
        body = await _safe_json(req)
        qty = int(body.get("quantity", 1))
        engs = int(body.get("engineers", 5))
        ok = game_getter().start_manufacture(iid, quantity=qty, assigned=engs)
        return _json({"ok": ok})

    async def mfg_cancel(req):
        iid = req.match_info["iid"]
        ok = game_getter().cancel_manufacture(iid)
        return _json({"ok": ok})

    async def battle_start(req):
        body = await _safe_json(req)
        ufo_id = body.get("ufo_id")
        game_getter().start_battle(ufo_id=ufo_id)
        return _json({"ok": True, "battle": game_getter().battle.snapshot()})

    async def battle_move(req):
        body = await _safe_json(req)
        g = game_getter()
        if g.battle is None:
            return _err("no active battle")
        r = g.battle.move_selected(int(body.get("dx", 0)), int(body.get("dy", 0)))
        return _json({"result": r, "battle": g.battle.snapshot()})

    async def battle_shoot(req):
        body = await _safe_json(req)
        g = game_getter()
        if g.battle is None:
            return _err("no active battle")
        r = g.battle.shoot_selected(
            int(body.get("tx", 0)), int(body.get("ty", 0)),
            mode=str(body.get("mode", "snap")),
        )
        return _json({"result": r, "battle": g.battle.snapshot()})

    async def battle_select(req):
        body = await _safe_json(req)
        g = game_getter()
        if g.battle is None:
            return _err("no active battle")
        direction = int(body.get("direction", 1))
        g.battle.cycle_selection(direction)
        return _json({"ok": True, "selected_idx": g.battle.selected_idx})

    async def battle_end_turn(_):
        g = game_getter()
        if g.battle is None:
            return _err("no active battle")
        events = g.battle.end_player_turn()
        # After the alien turn, check for game-ending outcome; if so, resolve.
        outcome = g.battle.outcome()
        if outcome is not None:
            g.end_battle(victory=(outcome == "victory"))
        return _json({"ok": True, "events": events, "outcome": outcome})

    async def battle_abort(_):
        g = game_getter()
        if g.battle is None:
            return _err("no active battle")
        g.end_battle(victory=False)
        return _json({"ok": True})

    async def get_log(req):
        try:
            since = int(req.query.get("since", "0"))
        except ValueError:
            since = 0
        g = game_getter()
        return _json({"log": g.log[since:], "count": len(g.log)})

    app.router.add_get("/state", state)
    app.router.add_post("/advance", advance)
    app.router.add_get("/research", research_list)
    app.router.add_post("/research/{rid}", research_start)
    app.router.add_delete("/research/{rid}", research_cancel)
    app.router.add_get("/manufacture", mfg_list)
    app.router.add_post("/manufacture/{iid}", mfg_start)
    app.router.add_delete("/manufacture/{iid}", mfg_cancel)
    app.router.add_post("/battle/start", battle_start)
    app.router.add_post("/battle/move", battle_move)
    app.router.add_post("/battle/shoot", battle_shoot)
    app.router.add_post("/battle/select", battle_select)
    app.router.add_post("/battle/end_turn", battle_end_turn)
    app.router.add_post("/battle/abort", battle_abort)
    app.router.add_get("/log", get_log)


async def _safe_json(req: web.Request) -> dict:
    try:
        return await req.json()
    except Exception:
        return {}


def start_agent_api(app_obj, port: int):
    """Start the aiohttp server alongside the Textual app's event loop."""
    loop = asyncio.get_event_loop()
    web_app = web.Application()
    _routes(web_app, lambda: app_obj.game)
    runner = web.AppRunner(web_app)
    loop.create_task(_serve(runner, port))
    return runner


async def _serve(runner: web.AppRunner, port: int) -> None:
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()


def start_agent_api_standalone(game: "Game", port: int) -> web.AppRunner:
    """Start the API in a dedicated event loop thread — used by --headless."""
    loop = asyncio.new_event_loop()
    web_app = web.Application()
    _routes(web_app, lambda: game)
    runner = web.AppRunner(web_app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "127.0.0.1", port)
    loop.run_until_complete(site.start())
    # Run the loop in a background thread.
    import threading
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return runner
