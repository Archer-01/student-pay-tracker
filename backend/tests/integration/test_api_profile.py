"""API tests for the student profile fields and the reworked PDF exports."""

import io
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.class_service import ClassService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_JOIN = "2023-03-05"


def pdf_text(raw: bytes) -> str:
    """Visible text of a PDF, lowercased with whitespace collapsed, so exports can be asserted on.

    Read with pypdf rather than by grepping the content stream: the PDFs embed their fonts, so
    the stream holds glyph codes, not text. ``split()`` also folds the no-break spaces French
    typography puts inside numbers and before punctuation into plain ones.
    """
    return " ".join(pdf_pages(raw))


def pdf_pages(raw: bytes) -> list[str]:
    """Each page's text, as `pdf_text` reads it."""
    reader = PdfReader(io.BytesIO(raw))
    return [" ".join((page.extract_text() or "").split()).lower() for page in reader.pages]


def _seed(db_session: Session) -> int:
    school_class = ClassService(db_session).create(level=ClassLevel.BAC2, name="Groupe A")
    pack = PackService(db_session).create(
        name="Maths seul", level=ClassLevel.BAC2, price=Decimal("150"), subjects=["Maths"]
    )
    student = StudentService(db_session).enroll(
        first_name="Amina",
        last_name="Benali",
        phone="+212600112233",
        join_date=date(2023, 3, 5),
        class_id=school_class.id,
        pack_id=pack.id,
        is_repeating=True,
    )
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("150")
    )
    return student.id


# --------------------------------------------------------------------------- #
# profile fields
# --------------------------------------------------------------------------- #


async def test_create_with_name_parts(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students",
        json={"first_name": "Amina", "last_name": "Benali", "join_date": _JOIN},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert (body["first_name"], body["last_name"], body["full_name"]) == (
        "Amina",
        "Benali",
        "Amina Benali",
    )
    assert body["is_repeating"] is False


async def test_create_without_a_surname(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students", json={"first_name": "Fatima Zahra", "join_date": _JOIN}
    )
    assert resp.json()["last_name"] is None
    assert resp.json()["full_name"] == "Fatima Zahra"


async def test_blank_first_name_is_422(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/students", json={"first_name": "  ", "join_date": _JOIN})
    assert resp.status_code == 422


async def test_patch_names_and_repeating(client: AsyncClient, db_session: Session) -> None:
    student_id = _seed(db_session)
    resp = await client.patch(
        f"/api/v1/students/{student_id}",
        json={"first_name": "Amine", "last_name": None, "is_repeating": False},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Amine"
    assert resp.json()["is_repeating"] is False


async def test_detail_carries_the_whole_profile(client: AsyncClient, db_session: Session) -> None:
    student_id = _seed(db_session)
    body = (
        await client.get(f"/api/v1/students/{student_id}", params={"as_of": "2023-06-30"})
    ).json()
    for field in (
        "full_name",
        "first_name",
        "last_name",
        "phone",
        "is_repeating",
        "join_date",
        "status",
        "school_class",
        "pack",
        "custom_price",
        "price_note",
        "monthly_price",
        "amount_owed",
        "months_overdue",
        "cumulative_drift",
        "next_expected_date",
        "payments_count",
        "total_paid",
        "first_payment_date",
    ):
        assert field in body, field
    assert body["first_payment_date"] == "2023-04-10"
    assert body["is_repeating"] is True


async def test_search_by_either_name_part(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    StudentService(db_session).enroll(
        first_name="Omar",
        last_name="Tazi",
        join_date=date(2023, 3, 5),
    )
    found = (await client.get("/api/v1/students", params={"q": "benali"})).json()
    assert [s["full_name"] for s in found] == ["Amina Benali"]
    assert len((await client.get("/api/v1/students", params={"q": "a"})).json()) == 2
    assert (await client.get("/api/v1/students", params={"q": "zzz"})).json() == []


# --------------------------------------------------------------------------- #
# ledger PDF
# --------------------------------------------------------------------------- #


async def test_ledger_pdf_reads_like_the_student_page(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    resp = await client.get(
        f"/api/v1/students/{student_id}/ledger.pdf", params={"as_of": "2023-06-30"}
    )
    assert resp.status_code == 200
    text = pdf_text(resp.content)

    # Who, and how to reach them.
    assert "payment history" in text
    assert "amina benali" in text
    assert "2bac — groupe a · maths seul · +212600112233" in text
    # The status card: March, May and June unpaid at the price of the pack.
    assert "3 months unpaid · 450 dh" in text
    assert "oldest unpaid month: march 2023." in text
    # The facts under it.
    assert "monthly price 150 dh" in text
    assert "student since 5 mar 2023" in text
    assert "total paid 150 dh" in text
    assert "days late in total 5 days" in text
    # The school year as tiles, then the one payment, saying how late it was.
    assert "2022–2023 school year" in text
    assert "april 2023 10 apr 2023 150 dh 5 days late" in text
    # Who made it, and the date its figures are for.
    assert "prof. teacher" in text
    assert "figures as of 30 jun 2023" in text
    assert "page 1 of 1" in text


async def test_ledger_pdf_is_localized(client: AsyncClient, db_session: Session) -> None:
    student_id = _seed(db_session)
    resp = await client.get(
        f"/api/v1/students/{student_id}/ledger.pdf",
        params={"as_of": "2023-06-30", "lang": "fr"},
    )
    text = pdf_text(resp.content)
    assert "historique des paiements" in text
    assert "3 mois impayés · 450 dh" in text
    assert "le plus ancien mois impayé : mars 2023." in text
    assert "tarif mensuel 150 dh" in text
    assert "inscrit le 5 mars 2023" in text
    assert "année 2022–2023" in text
    assert "avril 2023 10 avr. 2023 150 dh 5 jours de retard" in text
    assert "chiffres au 30 juin 2023" in text
    assert "page 1 sur 1" in text


async def test_ledger_pdf_of_a_student_who_has_paid_nothing_says_so(client: AsyncClient) -> None:
    """An empty table should be a sentence, not a lone header row."""
    created = await client.post(
        "/api/v1/students",
        json={"first_name": "Nouveau", "join_date": "2099-01-01"},
    )
    resp = await client.get(f"/api/v1/students/{created.json()['id']}/ledger.pdf")
    assert resp.status_code == 200
    assert "no payments received yet." in pdf_text(resp.content)


async def test_ledger_pdf_omits_the_agreed_price_row_when_there_is_none(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    text = pdf_text((await client.get(f"/api/v1/students/{student_id}/ledger.pdf")).content)
    assert "agreed price" not in text


async def test_ledger_pdf_shows_the_agreed_price_when_set(
    client: AsyncClient, db_session: Session
) -> None:
    """A parent reading a different price from their neighbour's sees why."""
    student_id = _seed(db_session)
    await client.patch(
        f"/api/v1/students/{student_id}",
        json={"custom_price": "90", "price_note": "remise fratrie"},
    )
    text = pdf_text((await client.get(f"/api/v1/students/{student_id}/ledger.pdf")).content)
    assert "monthly price 90 dh agreed price: remise fratrie" in text


async def test_a_long_history_carries_the_teacher_and_the_page_on_every_page(
    client: AsyncClient, db_session: Session
) -> None:
    student = StudentService(db_session).enroll(
        first_name="Youssef", phone=None, join_date=date(2023, 9, 5), custom_price=Decimal("300")
    )
    payments = PaymentService(db_session)
    for cycle in range(36):
        due = date(2023 + (8 + cycle) // 12, (8 + cycle) % 12 + 1, 5)
        payments.record_payment(
            student_id=student.id, cycle_number=cycle, paid_date=due, amount=Decimal("300")
        )
    resp = await client.get(
        f"/api/v1/students/{student.id}/ledger.pdf", params={"as_of": "2026-08-31"}
    )
    pages = pdf_pages(resp.content)
    assert len(pages) >= 2
    for number, page in enumerate(pages, start=1):
        assert "prof. teacher" in page
        assert f"page {number} of {len(pages)}" in page
        # The table's header is repeated wherever the table runs on.
        if "on time" in page:
            assert "month paid for" in page


# --------------------------------------------------------------------------- #
# roster + monthly PDFs
# --------------------------------------------------------------------------- #


async def test_roster_pdf_has_class_totals(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    class_id = (await client.get("/api/v1/classes")).json()[0]["id"]
    resp = await client.get(
        f"/api/v1/classes/{class_id}/roster.pdf", params={"as_of": "2023-06-30"}
    )
    text = pdf_text(resp.content)
    assert "class roster" in text
    assert "2bac — groupe a" in text
    assert "students 1" in text
    assert "unpaid 450 dh 1 student" in text
    assert "amina benali +212600112233" in text
    assert "3 months unpaid" in text
    assert "prof. teacher" in text


async def test_monthly_pdf_has_totals(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/reports/monthly.pdf", params={"year": 2023, "month": 6})
    text = pdf_text(resp.content)
    assert "monthly report" in text
    assert "june 2023" in text
    assert "collected in june" in text
    assert "unpaid on 30 jun 2023" in text
    # Each student's class sits under their name.
    assert "amina benali 2bac — groupe a" in text
    assert "prof. teacher" in text


# --------------------------------------------------------------------------- #
# A private note on each student
# --------------------------------------------------------------------------- #


async def test_a_note_is_kept_changed_and_cleared(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/students",
        json={"first_name": "Omar", "join_date": _JOIN, "note": "Paie le samedi, en espèces."},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    note = (await client.get(f"/api/v1/students/{sid}")).json()["note"]
    assert note == "Paie le samedi, en espèces."

    changed = await client.patch(f"/api/v1/students/{sid}", json={"note": "Père : Ahmed"})
    assert changed.json()["note"] == "Père : Ahmed"
    # Leaving the key out leaves it alone; an explicit null clears it.
    untouched = await client.patch(f"/api/v1/students/{sid}", json={"phone": "0611"})
    assert untouched.json()["note"] == "Père : Ahmed"
    cleared = await client.patch(f"/api/v1/students/{sid}", json={"note": None})
    assert cleared.json()["note"] is None


async def test_a_blank_note_is_no_note(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/students", json={"first_name": "Omar", "join_date": _JOIN, "note": "  \n "}
    )
    assert created.json()["note"] is None
    trimmed = await client.patch(
        f"/api/v1/students/{created.json()['id']}", json={"note": "  père : Ahmed  "}
    )
    assert trimmed.json()["note"] == "père : Ahmed"


async def test_a_note_has_a_length_limit(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students", json={"first_name": "Omar", "join_date": _JOIN, "note": "x" * 501}
    )
    assert resp.status_code == 422


async def test_the_note_stays_off_the_pdf_parents_receive(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    await client.patch(f"/api/v1/students/{student_id}", json={"note": "Père difficile à joindre"})
    text = pdf_text((await client.get(f"/api/v1/students/{student_id}/ledger.pdf")).content)
    assert "amina benali" in text
    assert "difficile" not in text
