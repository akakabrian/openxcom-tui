# OpenXcom TUI — design decisions

## Engine integration approach

**Chosen:** Pure-Python reimplementation of the minimum OpenXcom engine,
driving OXC-style data (geoscape globe, base view, research, manufacturing,
battlescape). Upstream repo is vendored under `engine/` as a reference
source and a ruleset YAML donor.

**Rejected: (a) SWIG-wrap the C++ core.** Unlike Micropolis (which
already had a `.i` file and a clean separation between sim + SDL
frontend), OpenXcom has no scripting layer, no headless mode, and its
state machine is threaded through the SDL main loop (event pump, audio
mixer, screen surface). The 250k-line C++ engine is 95% C++ and would
require SWIG bindings for ~40 classes plus SDL stubbing before we could
`simTick()` from Python.

**Rejected: (b) headless subprocess + save-state polling.** OpenXcom
cannot start without the original DOS UFO assets (UFO/, TFTD/
directories with `GEODATA/`, `MAPS/`, `ROUTES/`, `UFOGRAPH/`, `SOUND/`
subtrees). We can't legally redistribute those, and the user brief says
document-where-users-supply-it — not assume they did. Building a TUI
that only works once the user has procured Steam X-COM is a narrower
audience than a TUI that plays standalone.

**Rejected: (c.1) Parse and execute the full Xcom1Ruleset.** The
ruleset is ~8000 lines of YAML referencing dozens of sprite assets,
animation frames, sound indices, map block files, node routes. Most of
that is irrelevant to a TUI. We cherry-pick the *data* (research tree
names + costs, manufacturing items, craft stats, UFO types, alien ranks)
and implement the *mechanics* natively.

**Chosen route (c.2):** Pure-Python sim inspired by OpenXcom's
architecture (geoscape ↔ battlescape two-layer loop; base → research
→ manufacturing → craft → intercept → landing → battlescape tactical),
with a small hand-built ruleset seeded from OXC's
`bin/standard/xcom1/` YAML wherever the game data survives without
vendor assets. Mirrors the path taken for `julius-tui` and
`freeorion-tui` in this project set.

**Future upgrade path:** `openxcom_tui/engine.py` has a clean enough
surface (`Game.advance_day()`, `start_battle()`, action-per-soldier
API) that a future author could swap it for a SWIG or subprocess
binding without touching the TUI layer.

## Data sources

- `engine/openxcom/` — git-cloned OXC upstream (vendored, gitignored,
  fetched via `make bootstrap`). Used for:
  - Ruleset YAML reference (parsed selectively by `content.py`)
  - Constants we want to stay faithful to (TU costs, craft speeds,
    research tree shape)
- No vendor DOS assets required. README documents where users who own
  Steam X-COM can supply `UFO/` for eventual music / richer content —
  MVP plays without them.

## Scope for the timebox (MVP gates)

Following the skill's Stage-6 phasing, adapted to OpenXcom's two-layer
structure:

**Core (stages 1-4): geoscape basics**
- Mercator ASCII globe (world-wrap in X, clamped in Y)
- Rotatable view (arrow keys pan; Home recentres)
- Starting base placement + base interior grid (6×6 facility layout)
- Research queue with scientist allocation
- Manufacturing queue with engineer allocation
- Funding / month tick / Council report
- UFO detection + craft interception stub

**Phase A polish: battlescape MVP**
- Tile-based combat map (40×40)
- Soldier roster, selection, movement with TU cost
- Shooting action (snap/aimed/auto) consuming TUs
- Turn end, alien AI (trivial: random walk + shoot if visible)

**Phase B polish: submenus**
- UFOPaedia screen (research-gated entries)
- Tech tree graph view
- Base facility build menu
- Graphs (funding, research progress, kills)

**Phase C: agent REST API**
- `/state`, `/advance`, `/research/<id>`, `/manufacture/<id>`,
  `/battle/move`, `/battle/shoot`

**Phase D: sound** — optional, synthesised tones only; vendor WAV
support if the user supplies the `SOUND/` dir from Steam.

**Phase E: LLM advisor** — "should I intercept this UFO?" consults.

Explicit non-goals for timebox:
- Multi-base logistics beyond Base 1
- TFTD content (only UFO: Enemy Unknown)
- Psionics, cybernetics from OXCE+
- Night terror missions (just day landings)
- Tactical map procedural generation from OXC `MAPS/` — we hand-roll
  a small set of tilesets

## Directory layout

Mirrors simcity-tui / julius-tui / freeorion-tui:

```
openxcom-tui/
├── openxcom.py               # argparse entry point
├── pyproject.toml
├── Makefile                  # bootstrap / venv / run / test / clean
├── DECISIONS.md              # this file
├── README.md
├── LICENSE                   # GPLv3 (matches upstream)
├── engine/                   # vendored OXC source (reference only)
│   └── openxcom/
└── openxcom_tui/
    ├── __init__.py
    ├── engine.py             # pure-Python game state
    ├── content.py            # ruleset constants (research, items, craft)
    ├── geoscape.py           # globe projection + world tick
    ├── battlescape.py        # tactical combat sim
    ├── tiles.py              # glyph + style tables
    ├── app.py                # Textual App with mode switching
    ├── screens.py            # modal screens
    ├── agent_api.py          # aiohttp REST
    ├── sounds.py             # stdlib synth fallback
    └── tui.tcss
└── tests/
    ├── qa.py                 # TUI scenarios via Pilot
    ├── api_qa.py             # REST via aiohttp
    └── perf.py               # hot-path benchmarks
```

## Two-layer mode switching

OpenXcom's defining architectural feature is the geoscape↔battlescape
mode switch. We model this as two fully-compose-able Screens on a
single Textual App:

- `GeoscapeScreen` is the base screen: globe, base panel, event log.
- `BattlescapeScreen` is pushed when a mission starts and popped when
  it ends.
- Shared state lives on `app.game: Game`. Either screen reads/writes
  it; only one screen is compose-d at a time.

This keeps the TUI loop simple (one App, one CSS, one set of bindings)
while matching OXC's gameplay feel.

## Tile palette policy

Per the skill's visual palette rules:
- Geoscape ocean uses a 2-glyph `(x+y)&1` pattern `(≈, ~)`, land uses
  `(.·)`. Cities sparse `⌂` accents keyed on prime hash.
- Battlescape terrain gets 2-glyph patterns per class (grass, dirt,
  walls, doors). Soldiers are `☺ ☻` + empire colour, aliens are letters
  for rank (S=sectoid, F=floater, etc.) in red.
- Brightness budget: terrain dim, infrastructure medium, units bright,
  cursor + alert brightest. Animations at 2Hz (water ripple, cursor
  blink, UFO blip on geoscape).
