---
name: drift-invariants
description: Use when writing, reviewing, or extending app/services/schedule.py (due-date generation, days_late, cumulative_drift, next_expected_date) or its tests. Encodes the specific edge cases and property tests the domain logic must never lose, per sprint-planning.md's Sprint 1 and the override regression rule from Sprint 3.
---

# Drift calculation invariants

`services/schedule.py` is the highest-value, highest-risk code in this repo — per `sprint-planning.md`, "cutting Sprint 1's property tests to save time is a mistake." Any change to due-date generation, lateness, or cumulative drift must keep all of the following covered, not just make the immediate change pass.

## Required example tests

- The canonical scenario: join March 5, payments on April 10, May 10, June 10 → cumulative drift after June 10 must equal **15**. Reproduce the scoping doc's Table 3 exactly.
- Month-end anchor arithmetic: Jan 31 + 1 month → Feb 28 (or Feb 29 in a leap year), not Mar 3. Also Mar 31 → Apr 30.
- Use `date`, not `datetime`, to sidestep DST — but still add a test around a DST-transition date to prove it doesn't matter.

## Required hypothesis property tests

Write these with `hypothesis`, not just examples — the failure modes are the corner cases you don't think of:

1. `cumulative_drift` is monotonically non-decreasing as `as_of` moves forward.
2. `cumulative_drift` is always ≥ 0.
3. If every payment lands exactly on its expected due date, drift is 0.
4. Adding a payment can never decrease drift — only clearing an override can.
5. (Sprint 3+) An override never retroactively reduces `cumulative_drift` for cycles due *before* the override's effective date. This is a regression test that must exist before override logic is written, not after — it's the entire point of the audit-log design (overrides never touch `student.join_date` or existing payment rows).

## If a property test finds a bug

Add the failing case as a permanent example test alongside the fix — don't just fix and move on, since that exact input is what caught a real bug and should stay pinned.

## Exit bar

100% branch coverage on `services/schedule.py`. If a change to this file drops coverage, that's a signal a branch is untested, not that the threshold should move.
