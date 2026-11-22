# Backups

Every night at 3 a.m. (Morocco time) the app copies every database (the accounts and each
teacher's), packs them into one archive, encrypts it with your public key, and posts it to a
small Apps Script in your Google account, which files it in Drive under « Ardoise sauvegardes ».
Why it works this way: [decision 0012](decisions/0012-nightly-encrypted-backup-to-drive.md).

- **Only your private key can read a backup.** The server has the public half only.
- **Kept:** every copy of the last 30 days, then the first copy of each month for a year.
- **Watching it:** `GET /health` says `"backup": "ok"`, `"stale"` (no good copy for two days) or
  `"off"` (not set up). `ardoise backup status` gives the last success and the last error.
- After a restart, a copy is made at once if the last one is over a day old.

## Setting it up (once)

1. **Make the keys**, on your laptop, from `backend/`:

   ```bash
   uv run ardoise backup keygen
   ```

   Put the **private key** (`AGE-SECRET-KEY-…`) in your password manager, and keep one more
   copy (the file on your laptop). Lose both and no backup can ever be read. The **public key**
   (`age1…`) goes to the server in step 3.

2. **Create the Apps Script**, signed in to the Google account whose Drive should hold the
   backups:
   1. Go to [script.google.com](https://script.google.com), « New project », name it
      « Ardoise backups ».
   2. Replace the code with the content of `backend/ops/backup-drop.gs`, and save.
   3. « Project settings » › « Script properties » › add `SECRET` with a long random value
      (e.g. the output of `openssl rand -hex 32`).
   4. « Deploy » › « New deployment » › type « Web app »: execute as **Me**, access
      **Anyone**. Authorise it when asked (it needs your Drive). Copy the web app URL
      (`https://script.google.com/macros/s/…/exec`).

3. **Give the server the three values**, as Northflank secrets (runtime variables) on the
   service:

   | Variable | Value |
   |---|---|
   | `BACKUP_URL` | the web app URL from step 2.4 |
   | `BACKUP_SECRET` | the same value as the script's `SECRET` |
   | `BACKUP_PUBLIC_KEY` | the `age1…` public key from step 1 |

   `BACKUP_HOUR` (default 3, Morocco time) is optional.

4. **Check it end to end**, in the Northflank shell of the service:

   ```bash
   ardoise backup run      # "Uploaded ardoise-….tar.gz.age (N database(s))"
   ardoise backup status
   ```

   A file should appear in Drive › « Ardoise sauvegardes ». Then restore it on your laptop
   (below) once, so the first restore isn't during an incident.

If the script's code changes later, edit it in the Apps Script project and « Deploy » ›
« Manage deployments » › edit › « New version » (the URL stays the same).

## Restoring

1. Download the backup you want from Drive (`ardoise-YYYYMMDD-HHMMSS.tar.gz.age`; the time is
   UTC).
2. On your laptop, from `backend/`, with the private key in a file:

   ```bash
   uv run ardoise backup restore ~/Downloads/ardoise-….tar.gz.age --key-file key.txt --to restored
   ```

   It decrypts, unpacks every database into `restored/` and checks each one. (Without Ardoise,
   the `age` tool does the same: `age -d -i key.txt FILE | tar xz`.)
3. Look before replacing anything: run the app locally against the restored files
   (`DATABASE_URL=sqlite:///./restored/app.db just run`; the teachers' files sit beside it).
4. **Putting them back on Northflank** (the live files are in `/data`: `app.db` and
   `tenant-<id>.db`). In the service's shell:

   ```bash
   cd /data && mkdir -p before-restore && cp -a app.db* tenant-* before-restore/
   ```

   Then copy each restored file in. The files are small (about 100 KB), so pasting them works:
   on your laptop `base64 -i restored/tenant-1.db | pbcopy`, and in the shell
   `base64 -d > /data/tenant-1.db` followed by a paste and Ctrl-D. Delete any `-wal`/`-shm`
   file left beside a replaced database, then restart the service from the dashboard.

`ardoise db backup --to DIR` still makes a plain local copy on the same disk, for a quick safety
copy before a risky change; it is not an off-site backup.
