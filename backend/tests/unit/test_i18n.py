"""Unit tests for the i18n catalog and helpers."""

import re
from datetime import date
from decimal import Decimal

import pytest

from app.core.i18n import (
    MESSAGES,
    SUPPORTED_LOCALES,
    format_date,
    format_day,
    format_money,
    format_percent,
    month_name,
    month_short,
    normalize_locale,
    resolve_locale,
    translate,
)

NBSP = "\u00a0"


def test_translate_en_and_fr_with_params() -> None:
    assert translate("error.student_not_found", "en", student_id=7) == "No student with id 7"
    assert (
        translate("error.student_not_found", "fr", student_id=7) == f"Élève introuvable (n°{NBSP}7)"
    )


def test_translate_unknown_key_returns_key() -> None:
    assert translate("error.nope", "fr") == "error.nope"


def test_translate_unknown_locale_falls_back_to_default() -> None:
    assert translate("month.1", "de") == "January"  # falls back to en


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


# --------------------------------------------------------------------------- #
# Locale-aware values: French reads 26/10/2026 and 1 234,50
# --------------------------------------------------------------------------- #


def test_dates_are_day_first_in_french_and_unchanged_in_english() -> None:
    assert format_date(date(2026, 10, 26), "fr") == "26/10/2026"
    assert format_date(date(2026, 10, 26), "en") == "2026-10-26"


@pytest.mark.parametrize(
    ("day", "fr", "en"),
    [
        (date(2026, 11, 14), "14 nov. 2026", "14 Nov 2026"),
        (date(2026, 3, 5), "5 mars 2026", "5 Mar 2026"),
        (date(2026, 9, 1), "1 sept. 2026", "1 Sep 2026"),
        (date(2026, 8, 31), "31 août 2026", "31 Aug 2026"),
    ],
)
def test_a_day_reads_the_way_the_app_writes_it(day: date, fr: str, en: str) -> None:
    # The PDFs match the app's medium dates ("14 nov. 2026"), which a parent reads at a glance.
    # A no-break space keeps the day, month and year on one line.
    assert format_day(day, "fr") == fr.replace(" ", NBSP)
    assert format_day(day, "en") == en.replace(" ", NBSP)


def test_short_months_tell_every_month_apart() -> None:
    # The labels under a chart and on the month tiles, as in the app: "J" and "J" were ambiguous.
    fr = [month_short(m, "fr") for m in range(1, 13)]
    assert fr == ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct",
                  "Nov", "Déc"]
    assert [month_short(m, "en") for m in (1, 6, 7, 9)] == ["Jan", "Jun", "Jul", "Sep"]


def test_a_month_name_is_lowercase_inside_a_french_sentence() -> None:
    assert month_name(10, "fr") == "Octobre"
    assert month_name(10, "fr", in_sentence=True) == "octobre"
    assert month_name(10, "en", in_sentence=True) == "October"


@pytest.mark.parametrize(
    ("value", "fr", "en"),
    [
        (Decimal("250"), "250,00", "250.00"),
        (Decimal("1234.5"), f"1{NBSP}234,50", "1234.50"),
        (Decimal("0"), "0,00", "0.00"),
        (Decimal("1234567.891"), f"1{NBSP}234{NBSP}567,89", "1234567.89"),
    ],
)
def test_money_uses_a_decimal_comma_in_french(value: Decimal, fr: str, en: str) -> None:
    # A no-break space groups thousands so "1 234,50" never wraps between its digits. U+00A0
    # rather than the narrower U+202F: the PDFs draw with Helvetica, which cannot encode U+202F.
    assert format_money(value, "fr") == fr
    assert format_money(value, "en") == en


def test_message_params_are_formatted_for_the_locale() -> None:
    params = {"amount": Decimal("350.00"), "price": Decimal("300.00")}
    assert translate("error.payment_exceeds_price", "fr", **params) == (
        "Le montant (350,00) dépasse le tarif mensuel de l'élève (300,00)"
    )
    assert translate("error.payment_exceeds_price", "en", **params) == (
        "350.00 is more than this student's monthly price of 300.00"
    )
    dates = {"leave_date": date(2026, 9, 1), "entry_date": date(2026, 10, 1)}
    assert "(01/09/2026)" in translate("error.leave_before_entry", "fr", **dates)
    assert "(2026-09-01)" in translate("error.leave_before_entry", "en", **dates)


# --------------------------------------------------------------------------- #
# Plurals: "1 jour", "2 jours" — and French counts 0 as singular, English does not
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("count", "fr", "en"),
    [
        (0, f"0{NBSP}jour de retard", "0 days late"),
        (1, f"1{NBSP}jour de retard", "1 day late"),
        (8, f"8{NBSP}jours de retard", "8 days late"),
    ],
)
def test_lateness_is_pluralised_per_locale(count: int, fr: str, en: str) -> None:
    assert translate("pdf.days_late", "fr", count=count) == fr
    assert translate("pdf.days_late", "en", count=count) == en


def test_plural_keys_come_in_pairs() -> None:
    bases = {k.rsplit("_", 1)[0] for k in MESSAGES if k.endswith(("_one", "_other"))}
    for base in bases:
        assert f"{base}_one" in MESSAGES and f"{base}_other" in MESSAGES, base
        assert base not in MESSAGES, f"{base} has both a plain and a plural form"


# --------------------------------------------------------------------------- #
# French typography
# --------------------------------------------------------------------------- #


def test_french_punctuation_is_held_to_its_word_by_a_no_break_space() -> None:
    # French sets a space before : ; ? ! and inside « », and an ordinary space there lets the
    # punctuation wrap onto a line of its own. Every one must be a no-break space.
    loose = re.compile(r" [:;?!»]|« ")
    for key, translations in MESSAGES.items():
        assert not loose.search(translations["fr"]), f"{key}: {translations['fr']!r}"


def test_french_never_glues_punctuation_to_the_word() -> None:
    glued = re.compile(r"\w[;?!»]|«\w|\w:(?!\d)")
    for key, translations in MESSAGES.items():
        text = re.sub(r"\{[^}]*\}", "x", translations["fr"])  # {month:02d} is not punctuation
        assert not glued.search(text), f"{key}: {translations['fr']!r}"


@pytest.mark.parametrize(
    ("value", "fr", "en"),
    [
        (Decimal("25"), f"25{NBSP}%", "25%"),
        (Decimal("25.00"), f"25{NBSP}%", "25%"),
        (Decimal("12.5"), f"12,5{NBSP}%", "12.5%"),
    ],
)
def test_percentages_read_the_way_each_language_writes_them(
    value: Decimal, fr: str, en: str
) -> None:
    # Not formatted as money ("25,00"): a rate is written "25 %" in French, "25%" in English.
    assert format_percent(value, "fr") == fr
    assert format_percent(value, "en") == en
