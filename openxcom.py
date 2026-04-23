"""Entry point — ``python openxcom.py [--agent] [--headless]``."""

from __future__ import annotations

import argparse

from openxcom_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="openxcom-tui")
    p.add_argument("--seed", type=int, default=None,
                   help="RNG seed for reproducible playthroughs")
    p.add_argument("--start-battle", action="store_true",
                   help="skip straight to a tactical mission (debug)")
    p.add_argument("--agent", action="store_true",
                   help="start the agent HTTP API alongside the TUI")
    p.add_argument("--agent-port", type=int, default=8888,
                   help="port for the agent API (default: 8888)")
    p.add_argument("--headless", action="store_true",
                   help="no TUI, run sim + agent API only (implies --agent)")
    p.add_argument("--no-sound", action="store_true",
                   help="disable sound effects")
    args = p.parse_args()

    agent_port = args.agent_port if (args.agent or args.headless) else None
    run(
        seed=args.seed,
        agent_port=agent_port,
        headless=args.headless,
        start_battle=args.start_battle,
        sound=not args.no_sound,
    )


if __name__ == "__main__":
    main()
