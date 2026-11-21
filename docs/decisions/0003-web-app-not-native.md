# 0003. A web app (PWA), not a native app, for now

- Status: Accepted
- Decided: 2026-11-20 · Recorded: 2026-11-21

## Context
The developer would like Ardoise to feel like a real phone app, with notifications, and to have a
version for computers too. Its only user today is one teacher with an iPhone (and a Samsung
tablet). The teacher can't pay for a domain, hosting or a developer account, so Ardoise runs on
Northflank's free tier; the developer builds web apps, not mobile ones.

## Decision
Stay a single web app installed to the home screen (PWA): one backend, one frontend that adapts
from phone to desktop, with app-like touches (standalone display, offline reading, its own
status bar colours). Spend the effort on features and on the experience instead.

## Rejected
- **A native or React Native app**: a second codebase, App Store fees and review, for one user.
- **Separate mobile and web frontends**: twice the screens to keep in step.
- **A Capacitor wrapper now**: possible later around the same web app if notifications become
  essential; not needed yet.

## Consequences
- No reliable push notifications on iOS without more work (web push needs the installed PWA and
  the user's permission); no store presence.
- Revisit if notifications become a must, a second teacher joins on Android, or hosting changes.
