# 0013. Every backup copy is kept for a year

- Status: Accepted (replaces the retention rule in 0012)
- Decided: 2026-11-22 · Recorded: 2026-11-22

## Context
0012 kept every copy for 30 days, then the first copy of each month for a year. The Drive script
accepts any well-named file from whoever has its address and secret, so a junk file posted on the
1st became "the first copy of the month" and the real copies of that month were thrown away after
30 days (domain review, 2026-11-22).

## Decision
The script keeps every copy for 365 days, by the date Drive received it, and nothing else. At
about 100 KB a night that is under 40 MB a year, nothing for a Drive.

## Rejected
- **Keeping "the first copy of each month"**: junk can take a real copy's place (the above).
- **Checking a copy's content in the script**: it can't decrypt (it has no key, on purpose), so it
  can't tell a real copy from junk.

## Consequences
- After changing `backup-drop.gs`, the Apps Script project must be updated and redeployed as a
  new version (`docs/backups.md`); until then the old rule runs.
