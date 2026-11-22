# 0012. A nightly encrypted backup, sent to the developer's Google Drive

- Status: Accepted (replaces 0004); its retention rule is replaced by 0013
- Decided: 2026-11-22 · Recorded: 2026-11-22

## Context
The Northflank volume held the only copy of the data (0004): a lost volume, project or account
would lose every student's history. The data is tiny (about 100 KB per database) but holds real
names and phone numbers. A Northflank volume can only be mounted by the one service, so a
separate scheduled job can't read it. The developer didn't want a new account just to store a
few kilobytes a day.

## Decision
The app itself, every night at 3 a.m. Morocco time (and at startup when the last copy is over a
day old), copies every database safely while running, packs them in one archive, encrypts it to
the developer's `age` public key, and posts it to an Apps Script web app in the developer's
Google account, which saves it to a Drive folder and prunes by age (30 daily copies, then one a
month for a year). The private key stays with the developer (password manager plus a local
copy); the server never has it. Status is for the developer only: logs, `ardoise backup status`,
and `"backup"` in `/health`, which never fails the probe. `ardoise backup restore` decrypts and
checks a copy into a separate folder, never over the live files. Steps: `docs/backups.md`.

## Rejected
- **S3-style storage (Cloudflare R2, Backblaze B2)**: a new account for a few kilobytes a day.
- **The Google Drive API or rclone**: a Google Cloud project, an OAuth login and a refresh token
  to keep alive, for what a 60-line Apps Script does.
- **Emailing the file every night**: the inbox becomes the store, and nothing prunes it.
- **Litestream** (continuous replication): seconds of loss instead of a day, but another process
  in the container and a config to keep in step with each teacher's file; far more than a few
  payments a day need.
- **Northflank's own volume snapshots alone**: they stay on Northflank, so they don't survive
  losing the account or project. Worth turning on as well if the plan has them.

## Consequences
- Up to a day of entries can be lost (since the last 3 a.m. copy). Fine at this scale; revisit
  with Litestream if that ever matters.
- The script's address plus its secret is a write-only drop box: at worst someone adds junk
  files, which age-based pruning can't let push real copies out.
- Losing the private key loses every backup: it is kept in two places.
- A restore onto Northflank is a manual, documented step.
