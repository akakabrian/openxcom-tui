# openxcom-tui

Terminal-native clone of *UFO: Enemy Unknown* (OpenXCOM) — two-layer
gameplay (geoscape world strategy + battlescape tactical) rendered
entirely in a 200×60 text cell grid.

Built with [Textual](https://textual.textualize.io/). Pure-Python sim,
no C++ build step, no vendor DOS asset dependency — the game plays
standalone. See [DECISIONS.md](DECISIONS.md) for why we reimplement the
engine instead of binding to OpenXcom's C++ core.

## Install

```bash
make all      # python venv + pip install -e .
make run      # launch the TUI
```

Requires Python 3.10+, Linux or macOS. The `make bootstrap` target
will clone the upstream
[OpenXcom/OpenXcom](https://github.com/OpenXcom/OpenXcom) repo into
`engine/openxcom/` — used as a **reference** for ruleset YAML only, not
built or run. The `.venv` build works without it.

## Controls

### Geoscape (world map)

| key | action |
|-----|--------|
| ← ↑ ↓ → | move globe cursor |
| `space` / `p` | pause |
| `.` | advance 1 hour |
| `>` | advance 1 day |
| `r` | research menu |
| `m` | manufacture menu |
| `b` | base layout |
| `i` | intercept UFO |
| `u` | UFOpaedia |
| `h` | recenter on base |
| `t` | force-start a battle (debug) |
| `?` | help |
| `q` | quit |

### Battlescape (tactical)

| key | action |
|-----|--------|
| ← ↑ ↓ → | move crosshair |
| `w a s d` | step selected soldier |
| `tab` | cycle soldier selection |
| `f` | snap shot (25% TU) |
| `F` | aimed shot (60% TU) |
| `g` | auto burst (35% TU × 3) |
| `e` | end player turn |
| `x` | abort mission |

## Agent API

```bash
make headless                     # sim + REST on :8888, no TUI
python openxcom.py --agent        # TUI + REST on :8888
```

See [openxcom_tui/agent_api.py](openxcom_tui/agent_api.py) for the full
route list. In short: `GET /state`, `POST /advance`, research /
manufacture CRUD, and `POST /battle/{start,move,shoot,end_turn,abort}`.

## Tests

```bash
make test      # TUI scenarios via Textual Pilot (28 scenarios)
make test-api  # REST API scenarios
make perf      # hot-path benchmarks
```

## Original DOS / Steam UFO assets (optional)

OpenXCOM the original 1994 game requires the original DOS data files
(`UFO/GEODATA`, `UFO/UFOGRAPH`, `UFO/SOUND/`, etc.) to run. This
terminal port does **not** — it plays standalone from the hand-seeded
ruleset in [openxcom_tui/content.py](openxcom_tui/content.py).

If you own the original (available on
[Steam](https://store.steampowered.com/app/7760/XCOM_UFO_Defense/) for
a few dollars), you can drop the `UFO/` tree under `engine/openxcom/`
and future releases may pull optional flavour text / sound / music
from it. This repo never redistributes any of that data.

## Scope

MVP targets geoscape basics (globe, base, research, manufacturing,
funding, UFO detection + instant-resolve interception) and a
battlescape MVP (40×40 map, 8 soldiers, alien AI, move / shoot / end
turn). Explicitly out of scope for the timebox: psionics, multi-base
logistics, TFTD content, night missions, full tactical map generation
from the original `MAPS/` subtree. See [DECISIONS.md](DECISIONS.md) for
the full phasing.

## License

GPLv3 — matches upstream OpenXCOM. See [LICENSE](LICENSE).
