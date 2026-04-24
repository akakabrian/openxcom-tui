# DOGFOOD — openxcom

_Session: 2026-04-23T14:44:14, driver: pty, duration: 1.5 min_

**PASS** — ran for 1.1m, captured 7 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found 2 UX note(s). Game reached 35 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 1 coverage note(s) — see Coverage section.

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
  - All 13 score samples read '0'. Either scoring requires specific triggers or it's not wired to state().
- **[U2] Score never changed in state() during session**
  - Consider exposing score in /state or App attributes so agent-driven QA can verify progress.

## Coverage

- Driver backend: `pty`
- Keys pressed: 613 (unique: 52)
- State samples: 46 (unique: 35)
- Score samples: 46
- Milestones captured: 1
- Phase durations (s): A=44.0, B=14.7, C=9.1
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/openxcom-20260423-144304`

Unique keys exercised: -, ., /, 2, 3, 5, :, ;, >, ?, F, H, R, ], a, b, c, ctrl+l, d, delete, down, e, enter, escape, f, f2, g, h, i, k, l, left, m, n, p, page_down, q, question_mark, r, right ...

### Coverage notes

- **[CN1] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `openxcom-20260423-144304/milestones/first_input.txt` | key=up |
