"""Agent REST API QA.

Boots a headless API server on a free port, exercises every endpoint,
asserts response shape and key mutations. Exit code = failure count.

    python -m tests.api_qa
"""

from __future__ import annotations

import asyncio
import socket
import sys
import traceback

import aiohttp
from aiohttp import web

from openxcom_tui import agent_api
from openxcom_tui.engine import new_game


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _boot(game) -> tuple[web.AppRunner, int]:
    port = _free_port()
    web_app = web.Application()
    agent_api._routes(web_app, lambda: game)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner, port


async def scenarios() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    async def run(name: str, coro):
        try:
            await coro
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, f"AssertionError: {e}"))
        except Exception as e:
            results.append((name, False,
                            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))

    game = new_game(seed=7)
    runner, port = await _boot(game)
    base = f"http://127.0.0.1:{port}"

    async with aiohttp.ClientSession() as session:

        async def get(path):
            async with session.get(base + path) as r:
                return r.status, await r.json()

        async def post(path, body=None):
            async with session.post(base + path, json=body or {}) as r:
                return r.status, await r.json()

        async def delete(path):
            async with session.delete(base + path) as r:
                return r.status, await r.json()

        # --- state
        async def t_state():
            s, body = await get("/state")
            assert s == 200
            for k in ("mode", "date", "funds", "bases"):
                assert k in body, k
        await run("GET /state", t_state())

        # --- advance
        async def t_advance():
            _, before = await get("/state")
            s, body = await post("/advance", {"hours": 5})
            assert s == 200 and body.get("ok")
            _, after = await get("/state")
            assert after["hour"] == before["hour"] + 5
        await run("POST /advance", t_advance())

        # --- research list
        async def t_research_list():
            s, body = await get("/research")
            assert s == 200
            assert "available" in body
            assert isinstance(body["available"], list)
        await run("GET /research", t_research_list())

        # --- research start + cancel
        async def t_research_start_cancel():
            s, body = await post("/research/STR_MEDI_KIT", {"scientists": 3})
            assert s == 200 and body["ok"], body
            _, listing = await get("/research")
            ids = [p["id"] for p in listing["in_queue"]]
            assert "STR_MEDI_KIT" in ids
            s, body = await delete("/research/STR_MEDI_KIT")
            assert s == 200 and body["ok"]
            _, listing2 = await get("/research")
            ids2 = [p["id"] for p in listing2["in_queue"]]
            assert "STR_MEDI_KIT" not in ids2
        await run("POST+DELETE /research/<id>", t_research_start_cancel())

        # --- manufacture (requires research gating — pistol needs no prereq)
        async def t_manufacture_list():
            s, body = await get("/manufacture")
            assert s == 200
            assert "available" in body
        await run("GET /manufacture", t_manufacture_list())

        # --- battle: start → move → shoot → end turn → abort
        async def t_battle_lifecycle():
            s, body = await post("/battle/start", {})
            assert s == 200 and body["ok"]
            assert game.battle is not None
            # Move selected 1 step (may or may not succeed, but must not crash)
            s, body = await post("/battle/move", {"dx": 1, "dy": 0})
            assert s == 200 and "result" in body, body
            # Shoot at (20, 5)
            s, body = await post("/battle/shoot", {"tx": 20, "ty": 5, "mode": "snap"})
            assert s == 200 and "result" in body, body
            # End turn
            s, body = await post("/battle/end_turn", {})
            assert s == 200 and body["ok"]
            # Abort (if still active)
            if game.battle is not None:
                s, body = await post("/battle/abort", {})
                assert s == 200 and body["ok"]
            assert game.battle is None
        await run("POST /battle/* lifecycle", t_battle_lifecycle())

        # --- log endpoint
        async def t_log():
            s, body = await get("/log?since=0")
            assert s == 200
            assert "log" in body
            assert isinstance(body["log"], list)
        await run("GET /log", t_log())

    await runner.cleanup()
    return results


async def main() -> int:
    results = await scenarios()
    for name, ok, msg in results:
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines()[:5]:
                print(f"      {line}")
    failed = sum(1 for _, ok, _ in results if not ok)
    passed = len(results) - failed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
