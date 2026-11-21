"""Add, replace, remove and check the frontend's translation keys, in both catalogues at once.

    python i18n.py set home.greeting --fr "Bonjour {{name}} !" --en "Hello {{name}}!"
    python i18n.py set --file new-keys.json     # {"fr": {"a.b": "…"}, "en": {"a.b": "…"}}
    python i18n.py set home.greeting --fr "…" --en "…" --replace
    python i18n.py remove home.greeting
    python i18n.py check                        # what catalogues.test.ts checks, plus unused keys

Keys are dotted paths into the nested JSON. French spacing is fixed on the way in: a plain space
before : ; ? ! » or after « becomes a no-break space (U+00A0). Refuses a key in one language only,
placeholders that differ between the two, a plural without its pair, and overwriting an existing
key without --replace. Writes the files exactly as the repo keeps them (indent 2, UTF-8, final
newline), so the diff shows only what changed.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"
LOCALES = FRONTEND / "src" / "i18n" / "locales"
LANGS = ("fr", "en")
NBSP = " "
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
PLURAL = re.compile(r"_(one|other)$")


def load(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def save(lang: str, catalogue: dict) -> None:
    text = json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n"
    (LOCALES / f"{lang}.json").write_text(text, encoding="utf-8")


def leaves(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        if isinstance(value, dict):
            out |= leaves(value, f"{prefix}{key}.")
        else:
            out[prefix + key] = value
    return out


def get(catalogue: dict, key: str) -> object:
    node: object = catalogue
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def put(catalogue: dict, key: str, text: str) -> None:
    *parents, last = key.split(".")
    node = catalogue
    for part in parents:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            sys.exit(f"{key}: {part} is already a text, not a group")
        node = child
    if isinstance(node.get(last), dict):
        sys.exit(f"{key} is a group of keys, not a text")
    node[last] = text


def drop(catalogue: dict, key: str) -> bool:
    *parents, last = key.split(".")
    node = catalogue
    trail = []
    for part in parents:
        if not isinstance(node.get(part), dict):
            return False
        trail.append((node, part))
        node = node[part]
    if last not in node:
        return False
    del node[last]
    for parent, part in reversed(trail):  # remove groups left empty
        if parent[part]:
            break
        del parent[part]
    return True


def french_spacing(text: str) -> str:
    """Plain spaces where French needs no-break ones; nothing else is touched."""
    text = re.sub(r" ([:;?!»])", NBSP + r"\1", text)
    return text.replace("« ", "«" + NBSP)


def problems(fr_text: str, en_text: str, key: str) -> list[str]:
    found = []
    if set(PLACEHOLDER.findall(fr_text)) != set(PLACEHOLDER.findall(en_text)):
        found.append(f"{key}: placeholders differ (fr {PLACEHOLDER.findall(fr_text)}, "
                     f"en {PLACEHOLDER.findall(en_text)})")  # fmt: skip
    if re.search(r" [:;?!»]|« ", fr_text):
        found.append(f"{key}: plain space before French punctuation (use U+00A0)")
    if re.search(r"[\w\d][;?!»]|«\w|\w:", PLACEHOLDER.sub("x", fr_text)):
        found.append(f"{key}: French punctuation glued to the word before it")
    return found


def cmd_set(pairs: dict[str, dict[str, str]], replace: bool) -> None:
    catalogues = {lang: load(lang) for lang in LANGS}
    errors = []
    for key, texts in pairs.items():
        if set(texts) != set(LANGS):
            errors.append(f"{key}: give both --fr and --en")
            continue
        texts["fr"] = french_spacing(texts["fr"])
        errors += problems(texts["fr"], texts["en"], key)
        for lang in LANGS:
            if get(catalogues[lang], key) is not None and not replace:
                errors.append(f"{key} already exists in {lang}.json (pass --replace to change it)")
        if PLURAL.search(key):
            twin = PLURAL.sub(lambda m: "_other" if m[1] == "one" else "_one", key)
            if twin not in pairs and get(catalogues["en"], twin) is None:
                errors.append(f"{key}: plurals come in pairs, add {twin} too")
    if errors:
        sys.exit("\n".join(errors))
    for key, texts in pairs.items():
        for lang in LANGS:
            put(catalogues[lang], key, texts[lang])
    for lang in LANGS:
        save(lang, catalogues[lang])
    for key, texts in pairs.items():
        print(f"{key}\n  fr: {texts['fr']}\n  en: {texts['en']}")


def cmd_remove(keys: list[str]) -> None:
    catalogues = {lang: load(lang) for lang in LANGS}
    for key in keys:
        gone = [lang for lang in LANGS if drop(catalogues[lang], key)]
        print(f"{key}: removed from {', '.join(gone) or 'nowhere (not found)'}")
    for lang in LANGS:
        save(lang, catalogues[lang])


def used_in_source() -> str:
    files = subprocess.run(
        ["git", "ls-files", "src/*.ts", "src/*.tsx"], cwd=FRONTEND, capture_output=True, text=True
    ).stdout.split()
    return "\n".join(
        (FRONTEND / f).read_text(encoding="utf-8") for f in files if ".test." not in f
    )


def cmd_check() -> None:
    fr, en = leaves(load("fr")), leaves(load("en"))
    errors = [f"{k}: only in fr.json" for k in fr.keys() - en.keys()]
    errors += [f"{k}: only in en.json" for k in en.keys() - fr.keys()]
    for key in sorted(fr.keys() & en.keys()):
        errors += problems(fr[key], en[key], key)
    print("\n".join(errors) if errors else f"catalogues OK: {len(en)} keys in each")

    # Advisory: keys whose name appears nowhere in the source. A key built from a template
    # (t(`nav.${key}`)) counts as used through its prefix; one built any other way would still
    # show here, so read before deleting.
    source = used_in_source()
    dynamic = tuple(f"{p}." for p in re.findall(r"`([\w.]+)\.\$\{", source))
    unused = []
    for key in sorted(en):
        base = PLURAL.sub("", key)
        quoted = any(f"{q}{base}{q}" in source for q in "\"'`")
        if not quoted and not key.startswith(dynamic):
            unused.append(key)
    if unused:
        print(f"\nnot found in src/ ({len(unused)}), probably unused:")
        print("  " + "\n  ".join(unused))
    sys.exit(1 if errors else 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("key", nargs="?")
    s.add_argument("--fr")
    s.add_argument("--en")
    s.add_argument("--file", type=Path, help='{"fr": {key: text}, "en": {key: text}}')
    s.add_argument("--replace", action="store_true")
    r = sub.add_parser("remove")
    r.add_argument("keys", nargs="+")
    sub.add_parser("check")
    args = parser.parse_args()

    if args.cmd == "set":
        pairs: dict[str, dict[str, str]] = {}
        if args.file:
            data = json.loads(args.file.read_text(encoding="utf-8"))
            for lang in LANGS:
                for key, text in data.get(lang, {}).items():
                    pairs.setdefault(key, {})[lang] = text
        if args.key:
            pairs[args.key] = {lang: text for lang in LANGS if (text := getattr(args, lang))}
        if not pairs:
            parser.error("set needs a key with --fr/--en, or --file")
        cmd_set(pairs, args.replace)
    elif args.cmd == "remove":
        cmd_remove(args.keys)
    else:
        cmd_check()


if __name__ == "__main__":
    main()
