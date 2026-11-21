---
name: ardoise-demo
description: Run Ardoise with realistic demo data on scratch ports and take phone/desktop screenshots in light and dark. Use to see a UI change in the real app, check a screen on a phone-sized viewport, test offline mode against a production build, or gather screenshots for a review or an artifact. Never uses the developer's servers (8000, 5173) or real data.
---

# Ardoise demo and screenshots

Everything lives in a folder you choose (put it in your scratchpad); the developer's own servers
on **8000 and 5173** and their databases are never touched (`demo.sh` refuses those ports).

## Start, look, stop

```bash
S=<your scratchpad>/demo                         # one folder per demo
.claude/skills/ardoise-demo/scripts/demo.sh start "$S"          # dev:  app :5174, API :8001
.claude/skills/ardoise-demo/scripts/demo.sh start "$S" prod     # prod build on :5175 (service worker, offline)
.claude/skills/ardoise-demo/scripts/demo.sh status "$S"
.claude/skills/ardoise-demo/scripts/demo.sh stop "$S"           # by PID; data stays in $S/db
```

- Sign in as **aymen / demo-pass-123**. The first start migrates a fresh database, creates the
  account and seeds about twelve students (`scripts/seed.py`), all dated relative to today: on
  time, a little late, often late, owing one or two months, a custom price, a note, one due this
  week, one who left owing. Delete the folder to reseed.
- **dev** runs the current source (restart the web side after editing `vite.config.ts`); **prod**
  builds into `$S/dist` first, and is what offline checks need: serve it, load every screen, then
  stop the API (`demo.sh stop` stops both; kill `$(cat $S/api.pid)` for the API alone). Browser
  "offline" switches don't reach the service worker's own requests.
- Two demos at once (parallel agents): give each its own folder and ports,
  `API_PORT=8002 WEB_PORT=5176 demo.sh start "$S2"`.
- Logs: `$S/api.log`, `$S/web.log`, `$S/setup.log`, `$S/build.log`.

## Screenshots

```bash
cd .claude/skills/ardoise-demo/scripts
uv run --no-project --with playwright==1.58.0 python shoot.py "$S/shots" / /students /reports/monthly \
  --size phone,desktop --theme light,dark          # [--lang en] [--full] [--base http://127.0.0.1:5175]
```

One PNG per path × size × theme (`students-phone-dark.png`). Phone is 390×844 at 2× with touch,
like the teacher's iPhone; desktop 1280×800. Reduced motion, French unless `--lang en`. The theme
comes from the browser's colour scheme, as the app follows the device.

For a flow (opening a sheet, tapping a tile, a toast), write a short script next to your output
that reuses the signed-in page:

```python
import sys; sys.path.insert(0, "<repo>/.claude/skills/ardoise-demo/scripts")
from shoot import app, settle
with app(theme="dark") as page:                    # size="desktop", lang="en", base=...
    page.goto("/students/1"); settle(page)
    page.get_by_role("button", name="Encaisser").first.click()
    page.get_by_role("dialog").wait_for()
    page.screenshot(path="<out>/payment-sheet-dark.png")
```

Find elements by role and French label, as the teacher reads them (`get_by_role("button",
name="…")`, `get_by_label("…")`); `frontend/docs/screens.md` names what each screen shows.

## Checking a screen

Look at each screenshot rather than trusting that it was taken; read it with the Read tool.
Against `frontend/CLAUDE.md`'s "Mobile first" and "Look and feel":

- nothing cut off or overflowing at 390px; names not truncated by a pill;
- tap targets about 44px; text readable (17px base);
- status shown in words as well as colour; both themes legible (dark mode especially);
- French copy with its no-break spaces (no line starting with ":" or "?");
- the bottom bar and any fixed button clear of content.
