"""Unit tests for the i18n catalog and helpers."""

import pytest

from app.core.i18n import MESSAGES, SUPPORTED_LOCALES, normalize_locale, resolve_locale, translate


def test_translate_en_and_fr_with_params() -> None:
    assert translate("error.student_not_found", "en", student_id=7) == "No student with id 7"
    assert (
        translate("error.student_not_found", "fr", student_id=7)
        == "Aucun élève avec l'identifiant 7"
    )


def test_translate_unknown_key_returns_key() -> None:
    assert translate("error.nope", "fr") == "error.nope"


def test_translate_unknown_locale_falls_back_to_default() -> None:
    assert translate("status.active", "de") == "Active"  # falls back to en


@pytest.mark.parametrize(
    "header,expected",
    [
        ("fr", "fr"),
        ("fr-FR,fr;q=0.9,en;q=0.8", "fr"),
        ("en-US,en;q=0.9", "en"),
        ("de", "en"),  # unsupported -> default
        (None, "en"),
    ],
)
def test_resolve_locale(header: str | None, expected: str) -> None:
    assert resolve_locale(header) == expected


@pytest.mark.parametrize(
    "tag,expected",
    [("fr", "fr"), ("FR", "fr"), ("fr-CA", "fr"), ("en", "en"), ("de", None), (None, None)],
)
def test_normalize_locale(tag: str | None, expected: str | None) -> None:
    assert normalize_locale(tag) == expected


def test_every_message_has_all_supported_locales() -> None:
    for key, translations in MESSAGES.items():
        for locale in SUPPORTED_LOCALES:
            assert locale in translations, f"{key} missing {locale}"
            assert translations[locale].strip(), f"{key}[{locale}] is blank"
