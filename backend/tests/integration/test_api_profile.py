"""API tests for the student profile fields and the reworked PDF exports."""

import re
import zlib
from base64 import a85decode
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.class_service import ClassService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_JOIN = "2023-03-05"


def pdf_text(raw: bytes) -> str:
    """Visible text of a reportlab PDF, so exports can be asserted on rather than eyeballed.

    Content streams are ASCII85 + Flate; the drawn strings are the parenthesised literals.
    """
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        body = match.group(1).strip()
        for attempt in (lambda b: zlib.decompress(a85decode(b, adobe=True)),
                        lambda b: zlib.decompress(b),
                        lambda b: b):
            try:
                chunks.append(attempt(body))
                break
            except Exception:  # noqa: BLE001 - try the next decoding
                continue
    shown = re.findall(rb"\((?:\\.|[^()\\])*\)", b"\n".join(chunks))
    # Lowercased: the header labels are rendered in small caps, which is styling, not content.
    return "\n".join(s[1:-1].decode("latin-1") for s in shown).lower()


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


async def test_detail_carries_the_whole_profile(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    body = (
        await client.get(f"/api/v1/students/{student_id}", params={"as_of": "2023-06-30"})
    ).json()
    for field in (
        "full_name", "first_name", "last_name", "phone", "is_repeating", "join_date",
        "status", "school_class", "pack", "custom_price", "price_note", "monthly_price",
        "amount_owed", "months_overdue", "cumulative_drift", "next_expected_date",
        "payments_count", "total_paid", "first_payment_date",
    ):
        assert field in body, field
    assert body["first_payment_date"] == "2023-04-10"
    assert body["is_repeating"] is True


async def test_search_by_either_name_part(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    StudentService(db_session).enroll(
        first_name="Omar",
        last_name="Tazi",
        join_date=date(2023,
        3,
        5),
    )
    found = (await client.get("/api/v1/students", params={"q": "benali"})).json()
    assert [s["full_name"] for s in found] == ["Amina Benali"]
    assert len((await client.get("/api/v1/students", params={"q": "a"})).json()) == 2
    assert (await client.get("/api/v1/students", params={"q": "zzz"})).json() == []


# --------------------------------------------------------------------------- #
# ledger PDF
# --------------------------------------------------------------------------- #


async def test_ledger_pdf_shows_the_whole_profile(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    resp = await client.get(
        f"/api/v1/students/{student_id}/ledger.pdf", params={"as_of": "2023-06-30"}
    )
    assert resp.status_code == 200
    text = pdf_text(resp.content)

    assert "amina benali" in text
    assert "2bac" in text
    assert "maths seul" in text
    # Headline figures
    assert "monthly price" in text and "150.00" in text
    assert "total paid" in text
    assert "amount owed" in text
    assert "cumulative drift" in text
    # Detail block
    assert "+212600112233" in text
    assert "student since" in text and "2023-03-05" in text
    assert "first payment" in text and "2023-04-10" in text
    assert "repeating the year" in text
    # Provenance
    assert "as of 2023-06-30" in text


async def test_ledger_pdf_is_localized(client: AsyncClient, db_session: Session) -> None:
    student_id = _seed(db_session)
    resp = await client.get(
        f"/api/v1/students/{student_id}/ledger.pdf",
        params={"as_of": "2023-06-30", "lang": "fr"},
    )
    text = pdf_text(resp.content)
    assert "historique des paiements" in text
    assert "tarif mensuel" in text
    assert "redoublant" in text
    assert "premier paiement" in text
    # Accents survive the Helvetica/latin-1 round trip: "Impayé" in the status column.
    assert "impay\\351" in text


async def test_ledger_pdf_of_a_student_with_no_cycles_says_so(client: AsyncClient) -> None:
    """An empty export should be a sentence, not a lone header row."""
    created = await client.post(
        "/api/v1/students",
        json={"first_name": "Nouveau", "join_date": "2099-01-01"},
    )
    resp = await client.get(f"/api/v1/students/{created.json()['id']}/ledger.pdf")
    assert resp.status_code == 200
    assert "no billing cycles" in pdf_text(resp.content)


async def test_ledger_pdf_omits_the_agreed_price_row_when_there_is_none(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    text = pdf_text((await client.get(f"/api/v1/students/{student_id}/ledger.pdf")).content)
    assert "agreed price" not in text


async def test_ledger_pdf_shows_the_agreed_price_when_set(
    client: AsyncClient, db_session: Session
) -> None:
    student_id = _seed(db_session)
    await client.patch(
        f"/api/v1/students/{student_id}",
        json={"custom_price": "90", "price_note": "remise fratrie"},
    )
    text = pdf_text((await client.get(f"/api/v1/students/{student_id}/ledger.pdf")).content)
    assert "agreed price" in text
    assert "remise fratrie" in text


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
    assert "groupe a" in text
    assert "students" in text and "outstanding" in text
    assert "amina benali" in text


async def test_monthly_pdf_has_totals(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/reports/monthly.pdf", params={"year": 2023, "month": 6})
    text = pdf_text(resp.content)
    assert "monthly report" in text
    assert "collected" in text and "outstanding" in text
    assert "amina benali" in text
