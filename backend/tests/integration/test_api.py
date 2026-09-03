"""API tests — httpx.AsyncClient against the ASGI app, DB pointed at the per-test engine."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import Student, StudentStatus
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_FEE = Decimal("300")
_AS_OF = {"as_of": "2023-06-30"}


def _seed(db_session: Session) -> tuple[Student, Student]:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    amina = students.enroll(
        first_name="Amina", phone=None, join_date=date(2023, 3, 5), custom_price=_FEE
    )
    payments.record_payment(
        student_id=amina.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    payments.record_payment(
        student_id=amina.id, cycle_number=2, paid_date=date(2023, 5, 10), amount=_FEE
    )  # drift 5 + 5 = 10
    bilal = students.enroll(
        first_name="Bilal",
        phone=None,
        join_date=date(2023, 3, 5),
        custom_price=_FEE,
        status=StudentStatus.INACTIVE,
    )
    return amina, bilal


async def test_list_students(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/students", params=_AS_OF)
    assert resp.status_code == 200
    data = resp.json()
    assert {d["full_name"] for d in data} == {"Amina", "Bilal"}
    amina = next(d for d in data if d["full_name"] == "Amina")
    assert amina["cumulative_drift"] == 10
    # Cycles 0..3 due by Jun 30 (Mar/Apr/May/Jun); Apr & May paid → Mar & Jun unpaid.
    assert amina["months_overdue"] == 2


async def test_list_status_filter(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/students", params={"status": "active", **_AS_OF})
    assert resp.status_code == 200
    assert [d["full_name"] for d in resp.json()] == ["Amina"]


async def test_list_sort_drift_desc(client: AsyncClient, db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    low = students.enroll(
        first_name="Low", phone=None, join_date=date(2023, 3, 5), custom_price=_FEE
    )
    payments.record_payment(
        student_id=low.id, cycle_number=1, paid_date=date(2023, 4, 7), amount=_FEE
    )
    high = students.enroll(
        first_name="High", phone=None, join_date=date(2023, 3, 5), custom_price=_FEE
    )
    payments.record_payment(
        student_id=high.id, cycle_number=1, paid_date=date(2023, 4, 20), amount=_FEE
    )
    resp = await client.get("/api/v1/students", params={"sort": "drift_desc", **_AS_OF})
    assert [d["full_name"] for d in resp.json()] == ["High", "Low"]


async def test_months_overdue_counts_arrears_and_ignores_free_students(
    client: AsyncClient, db_session: Session
) -> None:
    students = StudentService(db_session)
    # Never-paid, fee > 0 → behind on every due cycle (0..3 by Jun 30 = 4).
    students.enroll(
        first_name="Behind",
        phone=None,
        join_date=date(2023,
        3,
        5),
        custom_price=_FEE,
    )
    # Free student (fee 0), never paid → owes nothing → 0.
    students.enroll(
        first_name="Free",
        phone=None,
        join_date=date(2023,
        3,
        5),
        custom_price=Decimal("0"),
    )
    resp = await client.get("/api/v1/students", params=_AS_OF)
    data = {d["full_name"]: d for d in resp.json()}
    assert data["Behind"]["months_overdue"] == 4
    assert data["Free"]["months_overdue"] == 0


@pytest.mark.parametrize(
    "params",
    [{"status": "bogus"}, {"sort": "bogus"}, {"as_of": "not-a-date"}],
)
async def test_bad_query_params_return_422(client: AsyncClient, params: dict[str, str]) -> None:
    resp = await client.get("/api/v1/students", params=params)
    assert resp.status_code == 422


async def test_student_detail(client: AsyncClient, db_session: Session) -> None:
    amina, _ = _seed(db_session)
    resp = await client.get(f"/api/v1/students/{amina.id}", params=_AS_OF)
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Amina"
    assert data["cumulative_drift"] == 10
    assert data["months_overdue"] == 2
    assert data["payments_count"] == 2
    assert Decimal(str(data["total_paid"])) == Decimal("600")
    assert data["next_expected_date"] == "2023-07-05"  # next due after 2023-06-30


@pytest.mark.parametrize("suffix", ["", "/ledger", "/drift"])
async def test_unknown_student_returns_404(client: AsyncClient, suffix: str) -> None:
    resp = await client.get(f"/api/v1/students/999{suffix}")
    assert resp.status_code == 404
    assert "detail" in resp.json()


async def test_ledger_endpoint(client: AsyncClient, db_session: Session) -> None:
    amina, _ = _seed(db_session)
    resp = await client.get(f"/api/v1/students/{amina.id}/ledger", params=_AS_OF)
    assert resp.status_code == 200
    data = resp.json()
    assert data["cumulative_drift"] == 10
    entries = {e["cycle_number"]: e for e in data["entries"]}
    assert entries[0]["paid_date"] is None  # enrollment month is an unpaid gap
    assert entries[1]["days_late"] == 5


async def test_drift_endpoint(client: AsyncClient, db_session: Session) -> None:
    amina, _ = _seed(db_session)
    resp = await client.get(f"/api/v1/students/{amina.id}/drift", params=_AS_OF)
    assert resp.status_code == 200
    assert resp.json()["cumulative_drift"] == 10


async def test_dashboard_summary_endpoint(client: AsyncClient, db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    a = students.enroll(

        first_name="A", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")

    )
    payments.record_payment(
        student_id=a.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=a.id, cycle_number=2, paid_date=date(2023, 5, 10), amount=Decimal("300")
    )
    b = students.enroll(

        first_name="B", phone=None, join_date=date(2023, 5, 5), custom_price=Decimal("200")

    )
    payments.record_payment(
        student_id=b.id, cycle_number=1, paid_date=date(2023, 6, 3), amount=Decimal("200")
    )

    resp = await client.get("/api/v1/dashboard/summary", params={"as_of": "2023-06-15"})
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(str(data["total_collected_this_month"])) == Decimal("200")
    assert Decimal(str(data["total_outstanding"])) == Decimal("800")
    assert [
        (latecomer["name"], latecomer["cumulative_drift"]) for latecomer in data["top_latecomers"]
    ] == [("A", 10)]


async def test_openapi_and_docs_render(client: AsyncClient) -> None:
    assert (await client.get("/openapi.json")).status_code == 200
    assert (await client.get("/docs")).status_code == 200


async def test_api_drift_matches_service(client: AsyncClient, db_session: Session) -> None:
    amina, _ = _seed(db_session)
    service_drift = LedgerService(db_session).cumulative_drift(amina.id, date(2023, 6, 30))
    resp = await client.get(f"/api/v1/students/{amina.id}/drift", params=_AS_OF)
    assert resp.json()["cumulative_drift"] == service_drift
