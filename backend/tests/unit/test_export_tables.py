"""Localized row-shaping for the PDF exports (headers, status column, formatting).

These test the pure `(header, rows)` helpers that feed the PDF renderer — localization is asserted
on strings here, since the rendered PDF's byte stream isn't greppable for the text.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.reports import _monthly_export
from app.api.students import _ledger_export, _ledger_filename, _ledger_subtitle, _slugify_name
from app.models import Student, StudentStatus
from app.services.ledger_service import LedgerEntry
from app.services.reports_service import MonthlyReport, MonthlyReportRow


def _entries() -> list[LedgerEntry]:
    return [
        # cycle 0: unpaid gap
        LedgerEntry(
            cycle_number=0,
            expected_due_date=date(2023, 3, 5),
            paid_date=None,
            days_late=None,
            amount=None,
            cumulative_drift=0,
        ),
        # cycle 1: paid 5 days late
        LedgerEntry(
            cycle_number=1,
            expected_due_date=date(2023, 4, 5),
            paid_date=date(2023, 4, 10),
            days_late=5,
            amount=Decimal("300"),
            cumulative_drift=5,
        ),
    ]


def test_ledger_export_english() -> None:
    header, rows = _ledger_export(_entries(), "en")
    assert header == [
        "Cycle",
        "Due date",
        "Paid date",
        "Days late",
        "Amount",
        "Cumulative drift",
        "Status",
    ]
    assert rows[0] == ["0", "2023-03-05", "", "", "", "0", "Unpaid"]
    assert rows[1] == ["1", "2023-04-05", "2023-04-10", "5", "300.00", "5", "5 days late"]


def test_ledger_export_french() -> None:
    header, rows = _ledger_export(_entries(), "fr")
    assert header == [
        "Cycle",
        "Date d'échéance",
        "Date de paiement",
        "Jours de retard",
        "Montant",
        "Retard cumulé",
        "Statut",
    ]
    assert rows[0][-1] == "Impayé"
    assert rows[1][-1] == "En retard de 5 jours"


def test_ledger_subtitle_name_and_phone() -> None:
    student = Student(name="Amïra", phone="+212600112233")
    assert _ledger_subtitle(student, "en") == "Amïra\nPhone: +212600112233"


def test_ledger_subtitle_name_only_when_no_phone() -> None:
    assert _ledger_subtitle(Student(name="Bilal", phone=None), "en") == "Bilal"


def test_ledger_subtitle_localizes_phone_label() -> None:
    student = Student(name="Youssef", phone="+212600112233")
    assert _ledger_subtitle(student, "fr") == "Youssef\nTéléphone : +212600112233"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Amina Benali", "amina-benali"),
        ("Amïra", "amira"),  # accents folded to ASCII
        ("  Omar   Tazi  ", "omar-tazi"),  # collapsed whitespace, trimmed
        ("Jean-Luc O'Neil", "jean-luc-o-neil"),  # punctuation to hyphens
        ("محمد", ""),  # no ASCII letters -> empty slug
    ],
)
def test_slugify_name(name: str, expected: str) -> None:
    assert _slugify_name(name) == expected


def test_ledger_filename_includes_name_slug() -> None:
    student = Student(id=7, name="Amina Benali", phone=None)
    assert _ledger_filename(student) == "student-7-amina-benali-ledger.pdf"


def test_ledger_filename_falls_back_to_id_only_for_unsluggable_name() -> None:
    student = Student(id=7, name="محمد", phone=None)
    assert _ledger_filename(student) == "student-7-ledger.pdf"


def _report(name: str = "Amïra") -> MonthlyReport:
    return MonthlyReport(
        year=2023,
        month=3,
        as_of=date(2023, 3, 31),
        total_collected=Decimal("300"),
        total_outstanding=Decimal("0"),
        rows=[
            MonthlyReportRow(
                student_id=1,
                name=name,
                status=StudentStatus.ACTIVE,
                fee=Decimal("300"),
                collected=Decimal("300"),
                cumulative_drift=0,
                outstanding=Decimal("0"),
            )
        ],
    )


def test_monthly_export_english() -> None:
    header, rows = _monthly_export(_report(), "en")
    assert header == [
        "Student ID",
        "Name",
        "Status",
        "Fee",
        "Collected",
        "Cumulative drift",
        "Outstanding",
    ]
    assert rows[0] == ["1", "Amïra", "Active", "300.00", "300.00", "0", "0.00"]


def test_monthly_export_french() -> None:
    header, rows = _monthly_export(_report(name="Youssef"), "fr")
    assert header == [
        "Identifiant élève",
        "Nom",
        "Statut",
        "Frais",
        "Encaissé",
        "Retard cumulé",
        "Solde dû",
    ]
    assert rows[0][2] == "Actif"  # status localized


def test_monthly_export_preserves_non_ascii_name() -> None:
    _, rows = _monthly_export(_report(name="Amïra"), "en")
    assert rows[0][1] == "Amïra"
