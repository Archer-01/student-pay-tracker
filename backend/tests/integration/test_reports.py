"""Reports & PDF exports: monthly totals invariant, PDF content-type/attachment, validation."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_PDF_MAGIC = b"%PDF-"


def _seed_month(db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    # A: fee 300, join Mar 5; pays Apr/May/Jun late (10th). June collection = 300.
    a = students.enroll(

        first_name="A", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")

    )
    for cycle, day in ((1, "04-10"), (2, "05-10"), (3, "06-10")):
        payments.record_payment(
            student_id=a.id,
            cycle_number=cycle,
            paid_date=date.fromisoformat(f"2023-{day}"),
            amount=Decimal("300"),
        )
    # B: fee 200, join Jun 5; pays cycle 0 on Jun 7 (2 late). June collection = 200.
    b = students.enroll(

        first_name="B", phone=None, join_date=date(2023, 6, 5), custom_price=Decimal("200")

    )
    payments.record_payment(
        student_id=b.id, cycle_number=0, paid_date=date(2023, 6, 7), amount=Decimal("200")
    )
    # C: inactive — excluded from the report entirely.
    students.enroll(
        first_name="C",
        phone=None,
        join_date=date(2023, 1, 5),
        custom_price=Decimal("500"),
        status=StudentStatus.INACTIVE,
    )


async def test_monthly_report_json_and_invariant(client: AsyncClient, db_session: Session) -> None:
    _seed_month(db_session)
    resp = await client.get("/api/v1/reports/monthly", params={"year": 2023, "month": 6})
    assert resp.status_code == 200
    data = resp.json()

    names = {row["name"] for row in data["rows"]}
    assert names == {"A", "B"}  # inactive C excluded

    rows = {row["name"]: row for row in data["rows"]}
    assert Decimal(str(rows["A"]["collected"])) == Decimal("300")
    assert rows["A"]["cumulative_drift"] == 15
    assert Decimal(str(rows["A"]["outstanding"])) == Decimal("300")  # Mar cycle unpaid
    assert Decimal(str(rows["B"]["collected"])) == Decimal("200")
    assert rows["B"]["cumulative_drift"] == 2

    # Invariant: totals == sum of the per-student rows.
    assert Decimal(str(data["total_collected"])) == sum(
        Decimal(str(r["collected"])) for r in data["rows"]
    )
    assert Decimal(str(data["total_outstanding"])) == sum(
        Decimal(str(r["outstanding"])) for r in data["rows"]
    )
    assert Decimal(str(data["total_collected"])) == Decimal("500")


async def test_monthly_report_pdf(client: AsyncClient, db_session: Session) -> None:
    _seed_month(db_session)
    resp = await client.get("/api/v1/reports/monthly.pdf", params={"year": 2023, "month": 6})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert 'filename="monthly-2023-06.pdf"' in disposition
    assert resp.content.startswith(_PDF_MAGIC)


async def test_ledger_pdf(client: AsyncClient, db_session: Session) -> None:
    student = StudentService(db_session).enroll(
        first_name="Amïra", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")
    )
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )  # 5 late; cycle 0 (Mar) and cycle 2 (May) remain unpaid gaps

    resp = await client.get(
        f"/api/v1/students/{student.id}/ledger.pdf", params={"as_of": "2023-06-30"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    # Filename carries a slug of the name (accents folded to ASCII).
    disposition = resp.headers["content-disposition"]
    assert f'filename="student-{student.id}-amira-ledger.pdf"' in disposition
    assert resp.content.startswith(_PDF_MAGIC)


async def test_ledger_pdf_unknown_student_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/students/999999/ledger.pdf")
    assert resp.status_code == 404


async def test_ledger_pdf_includes_name_and_phone(
    client: AsyncClient, db_session: Session, monkeypatch
) -> None:
    # Disable PDF compression so the rendered text is visible in the raw bytes.
    import reportlab.rl_config as rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0)
    student = StudentService(db_session).enroll(
        first_name="Amina",
        phone="+212600112233",
        join_date=date(2023, 3, 5),
        custom_price=Decimal("300"),
    )
    resp = await client.get(f"/api/v1/students/{student.id}/ledger.pdf")
    assert resp.status_code == 200
    assert b"Amina" in resp.content
    assert b"+212600112233" in resp.content


async def test_ledger_pdf_without_phone_shows_name_only(
    client: AsyncClient, db_session: Session, monkeypatch
) -> None:
    import reportlab.rl_config as rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0)
    student = StudentService(db_session).enroll(
        first_name="Bilal", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")
    )
    resp = await client.get(f"/api/v1/students/{student.id}/ledger.pdf")
    assert resp.status_code == 200
    assert b"Bilal" in resp.content
    assert b"Phone" not in resp.content  # no phone label when none provided


async def test_invalid_month_is_422(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/reports/monthly", params={"year": 2023, "month": 13})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Annual report API
# --------------------------------------------------------------------------- #


async def test_annual_report_endpoint(client: AsyncClient, db_session: Session) -> None:
    _seed_month(db_session)
    resp = await client.get("/api/v1/reports/annual", params={"year": 2023})
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2023
    assert [m["month"] for m in body["months"]] == list(range(1, 13))
    assert Decimal(body["total_collected"]) == sum(
        Decimal(m["collected"]) for m in body["months"]
    )


async def test_annual_report_pdf(client: AsyncClient, db_session: Session) -> None:
    from tests.integration.test_api_profile import pdf_text

    _seed_month(db_session)
    resp = await client.get("/api/v1/reports/annual.pdf", params={"year": 2023})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "annual-2023.pdf" in resp.headers["content-disposition"]
    text = pdf_text(resp.content)
    assert "annual revenue" in text and "2023" in text
    assert "collected" in text and "best month" in text
    assert "january" in text and "december" in text


async def test_annual_report_pdf_is_localized(client: AsyncClient, db_session: Session) -> None:
    from tests.integration.test_api_profile import pdf_text

    _seed_month(db_session)
    resp = await client.get(
        "/api/v1/reports/annual.pdf", params={"year": 2023, "lang": "fr"}
    )
    text = pdf_text(resp.content)
    assert "revenus annuels" in text
    assert "janvier" in text
    assert "meilleur mois" in text


async def test_annual_report_pdf_of_an_empty_year_says_so(client: AsyncClient) -> None:
    from tests.integration.test_api_profile import pdf_text

    resp = await client.get("/api/v1/reports/annual.pdf", params={"year": 1999})
    assert "no payments were recorded" in pdf_text(resp.content)
