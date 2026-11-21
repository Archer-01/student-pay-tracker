# 0006. Offline is read-only first; recording payments offline comes next

- Status: Accepted
- Decided: 2026-11-20 (phase 1 built) · Recorded: 2026-11-21

## Context
The teacher often works where there is no signal, and needs the app to be "super reliable".

## Decision
Phase 1: every screen readable offline. A service worker keeps the last server answer for each
read (network first), and the app copies every screen's data while online (`offlineWarmup.ts`).
Everything that saves is disabled offline. Details in `frontend/CLAUDE.md`, "Offline".

## Rejected (for now)
- **Recording payments offline straight away**: needs a queue of unsent payments replayed later,
  a safe replay (the backend's refusal of a duplicate month helps), telling the teacher when a
  queued payment is refused, and never losing one. Planned as phase 2, after the developer
  checks with the teacher how they actually work offline.
- **A full offline database in the browser** (sync engine): far more complexity than one user
  needs.

## Consequences
- Offline, the teacher can look things up but must note payments elsewhere until phase 2.
- A new screen must add its reads to `offlineWarmup.ts` with the same arguments, or it is blank
  offline.
