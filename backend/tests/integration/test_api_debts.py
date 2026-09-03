"""API tests for the leavers-with-debt list, write-offs, and the two warning moments."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.services.enrollment_service import EnrollmentService
from app.services.student_service import StudentService

_JOIN = date(2023, 3, 5)


def _left_owing(db_session: Session, first: str = "Amina", phone: str | None = None):
    student = StudentService(db_session).enroll(
        first_name=first, last_name="Benali", phone=phone,
        join_date=_JOIN, custom_price=Decimal("300"),
    )
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    return student


async def test_the_list_is_empty_when_nobody_left_owing(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/debts")).json()
    assert body == {"leavers": [], "total_owed": "0"}


async def test_the_list_carries_the_amount_and_total(
    client: AsyncClient, db_session: Session
) -> None:
    _left_owing(db_session)
    body = (await client.get("/api/v1/debts")).json()
    assert len(body["leavers"]) == 1
    leaver = body["leavers"][0]
    assert leaver["student"]["full_name"] == "Amina Benali"
    assert leaver["left_on"] == "2023-06-30"
    assert leaver["months_owed"] == 4
    assert Decimal(leaver["amount_owed"]) == Decimal("1200")
    assert Decimal(body["total_owed"]) == Decimal("1200")


async def test_a_students_own_debt_status(client: AsyncClient, db_session: Session) -> None:
    student = _left_owing(db_session)
    body = (await client.get(f"/api/v1/debts/{student.id}")).json()
    assert body["left_with_debt"] is True
    assert body["written_off"] is None


async def test_unknown_student_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/debts/999")).status_code == 404


async def test_write_off_clears_the_flag(client: AsyncClient, db_session: Session) -> None:
    student = _left_owing(db_session)
    resp = await client.post(
        f"/api/v1/debts/{student.id}/write-off", json={"reason": "parti à l'étranger"}
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["amount"]) == Decimal("1200")
    assert (await client.get("/api/v1/debts")).json()["leavers"] == []


async def test_write_off_needs_a_reason(client: AsyncClient, db_session: Session) -> None:
    student = _left_owing(db_session)
    assert (
        await client.post(f"/api/v1/debts/{student.id}/write-off", json={"reason": ""})
    ).status_code == 422


async def test_write_off_with_nothing_owed_is_409(
    client: AsyncClient, db_session: Session
) -> None:
    student = StudentService(db_session).enroll(first_name="A", join_date=_JOIN)
    resp = await client.post(f"/api/v1/debts/{student.id}/write-off", json={"reason": "x"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "nothing_to_write_off"


# --------------------------------------------------------------------------- #
# The two moments a warning matters
# --------------------------------------------------------------------------- #


async def test_returning_warns_but_succeeds(client: AsyncClient, db_session: Session) -> None:
    student = _left_owing(db_session)
    resp = await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-10-01"}
    )
    assert resp.status_code == 200  # never blocked
    body = resp.json()
    assert Decimal(body["amount_owed"]) == Decimal("1200")
    assert body["months_owed"] == 4
    assert "1200.00" in body["debt_warning"]


async def test_returning_without_debt_carries_no_warning(
    client: AsyncClient, db_session: Session
) -> None:
    student = StudentService(db_session).enroll(first_name="A", join_date=_JOIN)
    await client.post(f"/api/v1/students/{student.id}/leave", json={"leave_date": "2023-06-30"})
    resp = await client.post(
        f"/api/v1/students/{student.id}/return", json={"entry_date": "2023-10-01"}
    )
    assert resp.json()["debt_warning"] is None


async def test_the_return_warning_is_localized(
    client: AsyncClient, db_session: Session
) -> None:
    student = _left_owing(db_session)
    resp = await client.post(
        f"/api/v1/students/{student.id}/return",
        json={"entry_date": "2023-10-01"},
        headers={"Accept-Language": "fr"},
    )
    assert "est parti en devant" in resp.json()["debt_warning"]


async def test_matches_by_phone(client: AsyncClient, db_session: Session) -> None:
    _left_owing(db_session, phone="+212600112233")
    found = (
        await client.get("/api/v1/debts/matches", params={"phone": "+212600112233"})
    ).json()
    assert [m["student"]["full_name"] for m in found] == ["Amina Benali"]


async def test_matches_by_name_ignoring_case(client: AsyncClient, db_session: Session) -> None:
    _left_owing(db_session)
    found = (
        await client.get(
            "/api/v1/debts/matches", params={"first_name": "amina", "last_name": "BENALI"}
        )
    ).json()
    assert len(found) == 1


async def test_matches_returns_nothing_without_criteria(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/debts/matches")).json() == []


async def test_the_matches_route_is_not_shadowed_by_the_id_route(client: AsyncClient) -> None:
    """`/debts/matches` must not be parsed as `/debts/{student_id}` — hence the route order."""
    assert (await client.get("/api/v1/debts/matches", params={"phone": "x"})).status_code == 200


async def test_dashboard_reports_leaver_debt(client: AsyncClient, db_session: Session) -> None:
    _left_owing(db_session)
    body = (await client.get("/api/v1/dashboard/summary")).json()
    assert body["leavers_with_debt"] == 1
    assert Decimal(body["owed_by_leavers"]) == Decimal("1200")
