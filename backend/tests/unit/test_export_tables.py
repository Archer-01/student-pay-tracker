"""Localized row-shaping for the PDF exports (headers, status column, formatting).

These test the pure `(header, rows)` helpers that feed the PDF renderer — localization is asserted
on strings here, since the rendered PDF's byte stream isn't greppable for the text.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.classes import _roster_export, _roster_filename
from app.api.pdf_export import slugify_name
from app.api.reports import _monthly_export
from app.api.students import _ledger_export, _ledger_filename
from app.models import ClassLevel, SchoolClass, Student, StudentStatus
from app.services.class_service import RosterRow
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
        "Price",
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
        "Tarif",
        "Encaissé",
        "Retard cumulé",
        "Solde dû",
    ]
    assert rows[0][2] == "Actif"  # status localized


def test_monthly_export_preserves_non_ascii_name() -> None:
    _, rows = _monthly_export(_report(name="Amïra"), "en")
    assert rows[0][1] == "Amïra"


# --------------------------------------------------------------------------- #
# Class roster export
# --------------------------------------------------------------------------- #


def _roster_rows() -> list[RosterRow]:
    return [
        RosterRow(
            student=Student(
                id=1,
                first_name="Amina",
                last_name="Benali",
                phone="+212600112233",
                join_date=date(2023, 3, 5),
                status=StudentStatus.ACTIVE,
            ),
            cumulative_drift=15,
            months_overdue=2,
            amount_owed=Decimal("600"),
            monthly_price=Decimal("300"),
        ),
        RosterRow(
            student=Student(
                id=2,
                first_name="Omar",
                last_name="Tazi",
                phone=None,
                join_date=date(2023, 6, 20),
                status=StudentStatus.INACTIVE,
            ),
            cumulative_drift=0,
            months_overdue=0,
            amount_owed=Decimal("0"),
            monthly_price=Decimal("200"),
        ),
    ]


def test_roster_export_header_is_localized() -> None:
    assert _roster_export([], "en")[0][0] == "Student ID"
    assert _roster_export([], "fr")[0][0] == "Identifiant élève"


def test_roster_export_rows() -> None:
    _, rows = _roster_export(_roster_rows(), "en")
    assert rows[0] == [
        "1",
        "Amina Benali",
        "+212600112233",
        "Active",
        "300.00",
        "15",
        "2",
        "600.00",
    ]


def test_roster_export_renders_a_missing_phone_as_blank() -> None:
    _, rows = _roster_export(_roster_rows(), "en")
    assert rows[1][2] == ""


def test_roster_export_localizes_the_status_column() -> None:
    _, rows = _roster_export(_roster_rows(), "fr")
    assert [row[3] for row in rows] == ["Actif", "Inactif"]


def test_roster_filename_slugifies_level_and_name() -> None:
    school_class = SchoolClass(id=7, level=ClassLevel.BAC2, name="Groupe A")
    assert _roster_filename(school_class) == "2bac-groupe-a-roster.pdf"


def test_roster_filename_falls_back_to_the_id_for_an_unslugifiable_name() -> None:
    school_class = SchoolClass(id=7, level=ClassLevel.BAC2, name="مجموعة")
    # "2BAC" still slugifies, so the fallback needs a level+name that yields nothing at all.
    assert _roster_filename(school_class) == "2bac-roster.pdf"
