# 0005. A session cookie, and no CSRF token

- Status: Accepted
- Decided: when sign-in landed · Recorded: 2026-11-21

## Context
The app needs a sign-in gate for two accounts, with no email and no account management.

## Decision
Server-side sessions in an HttpOnly, `SameSite=Lax` cookie (90-day fixed expiry), argon2id
passwords, accounts created only with `ardoise users add`. No CSRF token. Details in
`backend/CLAUDE.md`, "Auth".

## Rejected
- **JWTs**: can't be revoked, and the browser would have to store a token JS can read.
- **A CSRF token**: the SPA is same-origin and every change is a JSON `POST`/`PATCH`/`DELETE`
  sent by `fetch`; with `SameSite=Lax` another site can't make those requests with the cookie.
- **Sign-up, password reset, OAuth**: no email, two users; each would be attack surface for
  nothing.

## Consequences
- The CSRF reasoning holds only while no `GET` changes data and the app stays same-origin.
  Revisit if either changes.
- A locked-out teacher is helped through the CLI on the server.
