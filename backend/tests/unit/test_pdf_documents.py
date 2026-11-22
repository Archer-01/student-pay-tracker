"""The PDFs' wording and colours: the pure helpers that decide what each document says.

The layout itself is checked by eye (and by the integration tests reading the rendered text);
what is pinned here is every choice of word and tone, in both languages, so paper and screen
keep saying the same thing.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.classes import _roster_filename
from app.api.pdf_documents import (
    footer_text,
    is_future,
    ledger_status,
    owed_pill,
    pack_label,
    roster_pill,
    tile_word,
    timing_pill,
)
from app.api.pdf_export import markup, money, slugify_name
from app.api.students import _ledger_filename
from app.models import ClassLevel, Pack, SchoolClass, Student, StudentStatus
from app.services.class_service import RosterRow
from app.services.ledger_service import LedgerEntry, StudentSummary
from app.services.pricing_service import PriceStatus
from app.services.school_year import MonthTile

NBSP = "\u00a0"


def _entry(cycle: int, due: date, paid: date | None = None, late: int | None = None) -> LedgerEntry:
    return LedgerEntry(
        cycle_number=cycle,
        expected_due_date=due,
        paid_date=paid,
        days_late=late,
        amount=Decimal("300") if paid else None,
        cumulative_drift=0,
    )


def _summary(months: int = 0, owed: str = "0") -> StudentSummary:
    return StudentSummary(
        cumulative_drift=5,
        months_overdue=months,
        amount_owed=Decimal(owed),
        next_expected_date=date(2026, 12, 5),
        payments_count=1,
        total_paid=Decimal("300"),
        first_payment_date=date(2026, 9, 5),
        average_days_late=0,
    )


# --------------------------------------------------------------------------- #
# Money and dates on paper
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "fr", "en"),
    [
        ("240.00", f"240{NBSP}DH", f"240{NBSP}DH"),
        ("1234.50", f"1{NBSP}234,50{NBSP}DH", f"1234.50{NBSP}DH"),
        ("0", f"0{NBSP}DH", f"0{NBSP}DH"),
    ],
)
def test_money_reads_the_way_the_app_writes_it(value: str, fr: str, en: str) -> None:
    # "240 DH", not "240,00": cents only when there are some.
    assert money(Decimal(value), "fr") == fr
    assert money(Decimal(value), "en") == en


def test_money_can_leave_the_currency_off_for_a_chart_label() -> None:
    assert money(Decimal("2100"), "fr", currency=False) == f"2{NBSP}100"


def test_digits_are_set_in_bricolage_so_a_zero_is_never_slashed() -> None:
    assert markup("Année 2026 & co") == ('Année <font face="Digits">2026</font> &amp; co')
    assert 'face="Digits-Bold"' in markup("300 DH", bold=True)


def test_the_footer_names_the_figures_date_only_when_it_is_another_day() -> None:
    made = date(2026, 11, 14)
    assert footer_text("fr", made) == f"Établi le 14{NBSP}nov.{NBSP}2026 avec Ardoise"
    assert footer_text("fr", made, made) == footer_text("fr", made)
    assert footer_text("en", made, date(2026, 10, 31)).endswith(
        f"figures as of 31{NBSP}Oct{NBSP}2026"
    )


def test_a_month_is_in_the_future_only_once_it_has_not_started() -> None:
    today = date(2026, 11, 14)
    assert not is_future(2026, 11, today)
    assert is_future(2026, 12, today)
    assert is_future(2027, 1, today)
    assert not is_future(2025, 12, today)


# --------------------------------------------------------------------------- #
# A student's history
# --------------------------------------------------------------------------- #


def _status(
    summary: StudentSummary, price_status: PriceStatus = "priced", **kw: object
) -> tuple[str, str | None, str]:
    args: dict[str, object] = {
        "enrolled": True,
        "left_on": None,
        "as_of": date(2026, 11, 14),
        "locale": "fr",
    } | kw
    entries = [
        _entry(0, date(2026, 9, 5), date(2026, 9, 5), 0),
        _entry(1, date(2026, 10, 5)),
        _entry(2, date(2026, 11, 5)),
    ]
    return ledger_status(summary, entries, price_status, **args)  # type: ignore[arg-type]


def test_what_is_owed_comes_first_naming_the_oldest_month() -> None:
    title, text, tone = _status(_summary(2, "600"))
    assert title == f"2{NBSP}mois impayés · 600{NBSP}DH"
    assert text == f"Le plus ancien mois impayé{NBSP}: Octobre 2026."
    assert tone == "bad"


def test_one_month_owed_is_amber_not_red() -> None:
    # As on the student page: one month behind is a nudge, two or more is a problem.
    assert _status(_summary(1, "300"))[2] == "warn"


def test_a_student_with_no_price_says_nothing_is_charged() -> None:
    title, text, tone = _status(_summary(), price_status="unset")
    assert (title, tone) == ("Sans tarif", "off")
    assert text is not None and "Rien n'est facturé" in text


def test_a_student_free_on_purpose_says_free_not_that_a_price_is_missing() -> None:
    # Decision 0011: as on the student page. This PDF goes to parents.
    title, text, tone = _status(_summary(), price_status="free")
    assert (title, tone) == ("Gratuit", "off")
    assert text is not None and "ne paie rien" in text


def test_a_student_who_left_says_since_when() -> None:
    title, text, tone = _status(_summary(), enrolled=False, left_on=date(2026, 10, 20))
    assert (title, tone) == ("Parti", "off")
    assert text == f"Ne fait plus partie des élèves depuis le 20{NBSP}oct.{NBSP}2026."


def test_a_student_who_left_without_a_date_has_no_second_line() -> None:
    assert _status(_summary(), enrolled=False)[1] is None


def test_a_student_up_to_date_is_told_when_the_next_payment_is_due() -> None:
    title, text, tone = _status(_summary(), locale="en")
    assert (title, tone) == ("Up to date", "ok")
    assert text == f"Next payment expected on 5{NBSP}Dec{NBSP}2026."


@pytest.mark.parametrize(
    ("state", "late", "fr"),
    [
        ("paid", None, "payé"),
        ("late", 9, f"9{NBSP}j"),
        ("due", None, "à payer"),
        ("away", None, "absent"),
        ("upcoming", None, "à venir"),
        ("none", None, ""),
    ],
)
def test_the_word_under_each_month_tile(state: str, late: int | None, fr: str) -> None:
    entry = _entry(1, date(2026, 10, 5), date(2026, 10, 14), late) if late else None
    tile = MonthTile(date(2026, 10, 1), state, entry)  # type: ignore[arg-type]
    assert tile_word(tile, "fr") == fr


def test_a_payment_says_on_time_or_how_late() -> None:
    on_time = timing_pill(_entry(0, date(2026, 9, 5), date(2026, 9, 5), 0), "fr")
    late = timing_pill(_entry(1, date(2026, 10, 5), date(2026, 10, 14), 9), "fr")
    assert (on_time.text, on_time.tone) == ("À l'heure", "ok")
    assert (late.text, late.tone) == (f"9{NBSP}jours de retard", "warn")


def test_the_pack_names_its_level_only_when_it_differs_from_the_class() -> None:
    bac2 = SchoolClass(id=1, level=ClassLevel.BAC2, name="Groupe A")
    pack = Pack(id=1, name="Maths seul", level=ClassLevel.BAC2, price=Decimal("150"))
    student = Student(id=1, first_name="Amina", school_class=bac2, pack=pack)
    assert pack_label(student, "fr") == "Maths seul"
    student.school_class = SchoolClass(id=2, level=ClassLevel.BAC1, name="Groupe A")
    assert pack_label(student, "fr") == "Maths seul · 2BAC"
    assert pack_label(Student(id=2, first_name="Omar"), "fr") == "Aucun pack"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Amina Benali", "amina-benali"),
        ("Amïra Bénali", "amira-benali"),
        ("  spaced  out  ", "spaced-out"),
        ("محمد", ""),  # no ASCII letters at all -> caller falls back to an id-only filename
    ],
)
def test_slugify_name(name: str, expected: str) -> None:
    assert slugify_name(name) == expected


def test_ledger_filename_includes_name_slug() -> None:
    student = Student(id=7, first_name="Amina", last_name="Benali", phone=None)
    assert _ledger_filename(student) == "student-7-amina-benali-ledger.pdf"


def test_ledger_filename_uses_a_mononym(student_id: int = 7) -> None:
    """A student with no surname still gets a readable filename."""
    student = Student(id=student_id, first_name="Fatima Zahra", last_name=None, phone=None)
    assert _ledger_filename(student) == "student-7-fatima-zahra-ledger.pdf"


def test_ledger_filename_falls_back_to_id_only_for_unsluggable_name() -> None:
    student = Student(id=7, first_name="محمد", last_name=None, phone=None)
    assert _ledger_filename(student) == "student-7-ledger.pdf"


# --------------------------------------------------------------------------- #
# The month and a class
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("owed", "price", "text", "tone"),
    [
        ("400", "priced", f"400{NBSP}DH", "bad"),
        ("0", "priced", "À jour", "ok"),
        ("0", "unset", "Sans tarif", "off"),
        ("0", "free", "Gratuit", "off"),
    ],
)
def test_what_a_student_still_owes_this_month(
    owed: str, price: PriceStatus, text: str, tone: str
) -> None:
    pill = owed_pill(Decimal(owed), price, "fr")
    assert (pill.text, pill.tone) == (text, tone)


def _roster_row(
    months: int = 0,
    price: str = "300",
    status: StudentStatus = StudentStatus.ACTIVE,
    price_status: PriceStatus = "priced",
) -> RosterRow:
    return RosterRow(
        student=Student(id=1, first_name="Amina", status=status, join_date=date(2023, 3, 5)),
        cumulative_drift=0,
        months_overdue=months,
        amount_owed=Decimal(price) * months,
        monthly_price=Decimal(price),
        price_status=price_status,
    )


@pytest.mark.parametrize(
    ("row", "text", "tone"),
    [
        (_roster_row(2), f"2{NBSP}mois impayés", "bad"),
        (_roster_row(1), f"1{NBSP}mois impayé", "warn"),
        (_roster_row(), "À jour", "ok"),
        (_roster_row(price="0", price_status="unset"), "Sans tarif", "off"),
        (_roster_row(price="0", price_status="free"), "Gratuit", "off"),
        (_roster_row(2, status=StudentStatus.INACTIVE), "Ancien élève", "off"),
    ],
)
def test_where_each_student_of_a_class_stands(row: RosterRow, text: str, tone: str) -> None:
    pill = roster_pill(row, "fr")
    assert (pill.text, pill.tone) == (text, tone)


def test_roster_filename_slugifies_level_and_name() -> None:
    school_class = SchoolClass(id=7, level=ClassLevel.BAC2, name="Groupe A")
    assert _roster_filename(school_class) == "2bac-groupe-a-roster.pdf"


def test_roster_filename_falls_back_to_the_id_for_an_unslugifiable_name() -> None:
    school_class = SchoolClass(id=7, level=ClassLevel.BAC2, name="مجموعة")
    # "2BAC" still slugifies, so the fallback needs a level+name that yields nothing at all.
    assert _roster_filename(school_class) == "2bac-roster.pdf"
