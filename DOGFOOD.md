# DOGFOOD — openxcom

_Session: 2026-04-23T13:25:22, driver: pty, duration: 3.0 min_

**PASS** — ran for 1.9m, captured 9 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found 2 UX note(s). Game reached 36 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 1 coverage note(s) — see Coverage section.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)
- **[U1] score never changes during normal play**
  - All 20 score samples read '0'. Either scoring requires specific triggers or it's not wired to state().
- **[U2] Score never changed in state() during session**
  - Consider exposing score in /state or App attributes so agent-driven QA can verify progress.

## Coverage

- Driver backend: `pty`
- Keys pressed: 968 (unique: 45)
- State samples: 47 (unique: 36)
- Score samples: 20
- Milestones captured: 1
- Phase durations (s): A=84.2, B=11.8, C=18.1
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/openxcom-20260423-132326`

Unique keys exercised: ., /, 3, 5, :, >, ?, F, H, R, ], a, b, c, d, down, e, enter, escape, f, f2, g, h, i, k, left, m, n, p, q, question_mark, r, right, s, shift+slash, shift+tab, space, t, tab, u ...

### Coverage notes

- **[CN1] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `openxcom-20260423-132326/milestones/first_input.txt` | key=up |
