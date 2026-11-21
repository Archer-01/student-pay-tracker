# 0010. The CLI is an admin tool, not a second app

- Status: Accepted (replaces 0008)
- Decided: 2026-11-21 · Recorded: 2026-11-21

## Context
The `ardoise` CLI was built in sprint 4, before the API and long before the app, as the way to
enter and inspect data. Since then the app has taken over everything the teacher does, and the
CLI fell behind: packs still in the old price-grid model, no way to edit a student's details,
nothing for the school's share. Its payment commands also skipped checks that lived only in
the API's request schemas, so a future paid date inflated drift (5 → 1726 days in a test). The
developer uses it only as admin access, from a shell on the Northflank host.

## Decision
The CLI keeps only what the app can't do:

- **accounts**: `users add | list | passwd | deactivate | activate` (there is no sign-up,
  0005);
- **operations**: `db migrate | backup | reset` (reset is dev-only), and `openapi` for
  `npm run gen:api`;
- **deleting a student for good**, which the app never does, behind typing the student's name;
- **read-only lookups** for support: `students list | show`, `debts list`, `share list`.

Everything that writes the teacher's data (students, payments, overrides, classes, packs,
leaving and returning, write-offs) is done in the app only. The checks the CLI used to skip
(no paid date in the future, at most two decimals) now live in `PaymentService`, so every
caller gets them.

## Rejected
- **Keeping the CLI level with the app**: a second door to the same data, with its own options
  and validation to keep in step on every change. That gap is where the drift bug came from.
- **Removing the CLI entirely**: accounts and backups need it, and it keeps working when nobody
  can sign in.

## Consequences
- Fixing data from a terminal while the app is down isn't possible; if a case comes up, add
  that one command deliberately, through the services.
- A command added later reads or writes through the services, never the database directly, and
  gets a test in `tests/integration/test_cli.py`.
