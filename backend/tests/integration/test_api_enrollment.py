"""API tests for leaving, returning, and what an absence does to the numbers."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_JOIN = "2023-03-05"


def _student(db_session: Session, price: str = "300"):
    return StudentService(db_session).enroll(
        first_name="Amina", join_date=date(2023, 3, 5), custom_price=Decimal(price)
    )


async def test_a_new_student_has_one_open_period(
    client: AsyncClient, db_session: Session
) -> None:
    student = _student(db_session)
    periods = (await client.get(f"/api/v1/students/{student.id}/periods")).json()
    assert len(periods) == 1
    assert periods[0]["entry_date"] == _JOIN
    assert periods[0]["leave_date"] is None


async def test_leave_and_return(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    left = await client.post(
        f"/api/v1/students/{student.id}/leave",
        json={"leave_date": "2023-06-30", "reason": "moved away"},
    )
    assert left.status_code == 200
    assert left.json()["leave_date"] == "2023-06-30"
    assert (await client.get(f"/api/v1/students/{student.id}")).json()["status"] == "inactive"

    back = await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-10-01"}
    )
    assert back.status_code == 200
    assert (await client.get(f"/api/v1/students/{student.id}")).json()["status"] == "active"
    assert len((await client.get(f"/api/v1/students/{student.id}/periods")).json()) == 2


async def test_returning_does_not_move_the_join_date(
    client: AsyncClient, db_session: Session
) -> None:
    student = _student(db_session)
    await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-06-30"}
    )
    await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2024-01-01"}
    )
    assert (await client.get(f"/api/v1/students/{student.id}")).json()["join_date"] == _JOIN


async def test_leaving_twice_is_409(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    body = {"leave_date": "2023-06-30"}
    await client.post(f"/api/v1/students/{student.id}/leave", json=body)
    resp = await client.post(f"/api/v1/students/{student.id}/leave", json=body)
    assert resp.status_code == 409
    assert resp.json()["code"] == "period_not_open"


async def test_returning_while_present_is_409(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    resp = await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-10-01"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "period_already_open"


async def test_leaving_before_arriving_is_409(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    resp = await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2022-01-01"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "leave_before_entry"


async def test_months_away_are_not_owed(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session, price="300")
    before = (
        await client.get(f"/api/v1/students/{student.id}", params={"as_of": "2023-10-31"})
    ).json()
    assert before["months_overdue"] == 8

    await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-05-31"}
    )
    await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-09-01"}
    )
    after = (
        await client.get(f"/api/v1/students/{student.id}", params={"as_of": "2023-10-31"})
    ).json()
    assert after["months_overdue"] == 5
    assert Decimal(after["amount_owed"]) == Decimal("1500")


async def test_ledger_marks_away_months(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-05-31"}
    )
    await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-09-01"}
    )
    entries = (
        await client.get(f"/api/v1/students/{student.id}/ledger", params={"as_of": "2023-10-31"})
    ).json()["entries"]
    assert [e["cycle_number"] for e in entries if e["suspended"]] == [3, 4, 5]


async def test_leaving_keeps_drift_already_accrued(
    client: AsyncClient, db_session: Session
) -> None:
    student = _student(db_session)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 20), amount=Decimal("300")
    )
    params = {"as_of": "2024-06-30"}
    before = (await client.get(f"/api/v1/students/{student.id}", params=params)).json()
    await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-05-31"}
    )
    after = (await client.get(f"/api/v1/students/{student.id}", params=params)).json()
    assert after["cumulative_drift"] == before["cumulative_drift"] == 15


async def test_amend_a_period(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    left = await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-06-30"}
    )
    resp = await client.patch(
        f"/api/v1/students/{student.id}/periods/{left.json()['id']}",
        json={"leave_date": "2023-07-31"},
    )
    assert resp.status_code == 200
    assert resp.json()["leave_date"] == "2023-07-31"


async def test_amend_rejects_unknown_fields(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    period_id = (await client.get(f"/api/v1/students/{student.id}/periods")).json()[0]["id"]
    resp = await client.patch(
        f"/api/v1/students/{student.id}/periods/{period_id}", json={"nope": 1}
    )
    assert resp.status_code == 422


async def test_return_is_never_blocked_by_debt(client: AsyncClient, db_session: Session) -> None:
    """The teacher decides whether to re-admit someone who owes — the app doesn't gate it."""
    student = _student(db_session, price="300")
    await client.post(
        f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-06-30"}
    )
    owed = (
        await client.get(f"/api/v1/students/{student.id}", params={"as_of": "2023-06-30"})
    ).json()["amount_owed"]
    assert Decimal(owed) > 0
    resp = await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2024-01-01"}
    )
    assert resp.status_code == 200


async def test_error_detail_is_localized(client: AsyncClient, db_session: Session) -> None:
    student = _student(db_session)
    resp = await client.post(
        f"/api/v1/students/{student.id}/return",
        json={"entry_date": "2023-10-01"},
        headers={"Accept-Language": "fr"},
    )
    assert "déjà présent" in resp.json()["detail"]
