---
name: add-i18n-keys
description: Add, change or remove user-facing text in Ardoise, in French and English together. Use whenever a frontend string goes into src/i18n/locales/{fr,en}.json or a backend message into app/core/i18n.py, or to find unused or broken translation keys. Fixes French spacing (no-break spaces), refuses one-language keys, mismatched placeholders and half plural pairs.
---

# Adding text to Ardoise

The teacher reads the app in **French**; English must exist too. Every string lives in both
languages, and French follows French typography: a **no-break space (U+00A0)** before `: ; ? !`
and inside `« »`, so the punctuation never wraps onto a line of its own on a phone. Tests in both
apps fail otherwise. Write French that reads naturally to a teacher, not a word-for-word
translation, and keep it short: most of it is read on a 390px screen.

## Frontend: use the script, not hand edits

```bash
I=.claude/skills/add-i18n-keys/scripts/i18n.py
python3 $I set home.greeting --fr "Bonjour {{name}} !" --en "Hello {{name}}!"
python3 $I set --file keys.json            # many at once: {"fr": {"a.b": "…"}, "en": {"a.b": "…"}}
python3 $I set home.greeting --fr "…" --en "…" --replace     # change an existing text
python3 $I remove home.greeting
python3 $I check                           # both catalogues, plus keys nothing in src/ uses
```

It writes both `frontend/src/i18n/locales/{fr,en}.json` in the repo's exact format, turns plain
spaces before French punctuation into U+00A0, and refuses: a key in one language only,
`{{placeholders}}` that differ between the two, `_one` without `_other`, a key that already exists
(without `--replace`). Type the French with ordinary spaces; the script fixes them.

Then, in the component:

- `const { t } = useTranslation();` and `t("home.greeting", { name })`.
- **Counts**: keys `x_one` / `x_other`, called as `t("x", { count })`; never `{n} {t("élèves")}`
  ("1 élèves"). French counts 0 as singular.
- **No `defaultValue`** in `t()`: it hides a missing key from the tests.
- Money and dates go through `formatMoney` / `formatDate` (`lib/money.ts`, `lib/dates.ts`), not
  into the text by hand.
- Tests run in English and assert on the English copy, so a missing key fails a test.

`check` lists keys found nowhere in `src/`; keys built from a template (`` t(`nav.${key}`) ``) are
recognised by their prefix. Grep before deleting one that might be built another way.

## Backend: `app/core/i18n.py`

API error messages and PDF text live in `MESSAGES`, a Python dict
`key -> {"en": …, "fr": …}` with `str.format` params (`{student_id}`, not `{{…}}`). Edit it
directly:

- write the no-break space as the escape `\u00a0` so it stays visible in the source;
- plurals as `<key>_one` / `<key>_other`, called with the bare key and a `count` param;
- pass `date` and `Decimal` values as params, never pre-formatted strings: `translate` formats
  them for the locale;
- domain errors carry a `code` (`error.<code>`) and params from the service; only the API layer
  translates.

`uv run pytest tests/unit/test_i18n.py` checks completeness and typography.

## Done

- `cd frontend && npm test` (or `npx vitest run src/i18n`) for the catalogues, plus the screens
  that use the text.
- Look at it on a phone (skill `ardoise-demo`): French is often longer than English and is what
  gets cut off.
