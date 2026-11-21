"""API tests for packs and student pack assignments."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.pack_service import PackService
from app.services.student_service import StudentService

_JOIN = "2023-03-05"


def _offering(db_session: Session, name: str = "Maths seul") -> None:
    service = PackService(db_session)
    for level, price in {ClassLevel.AC1: Decimal("100"), ClassLevel.BAC2: Decimal("150")}.items():
        service.create(name=name, level=level, price=price, subjects=["Maths"])


def _student(db_session: Session, **kw: object):
    return StudentService(db_session).enroll(
        first_name="Amina", phone=None, join_date=date(2023, 3, 5), **kw
    )


# --------------------------------------------------------------------------- #
# packs
# --------------------------------------------------------------------------- #


async def test_create_and_list_packs(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/packs",
        json={"name": "Maths seul", "level": "2BAC", "price": "150", "subjects": ["Maths"]},
    )
    assert resp.status_code == 201
    assert resp.json()["subjects"] == ["Maths"]
    listed = (await client.get("/api/v1/packs")).json()
    assert [(p["name"], p["level"], p["price"]) for p in listed] == [
        ("Maths seul", "2BAC", "150.00")
    ]


async def test_create_pack_without_subjects_is_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/packs",
        json={"name": "X", "level": "2BAC", "price": "1", "subjects": []},
    )
    assert resp.status_code == 422


async def test_duplicate_pack_is_409(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    resp = await client.post(
        "/api/v1/packs",
        json={"name": "Maths seul", "level": "2BAC", "price": "9", "subjects": ["Maths"]},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "duplicate_pack"


async def test_filter_by_level_and_active(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    by_level = (await client.get("/api/v1/packs", params={"level": "1AC"})).json()
    assert [p["level"] for p in by_level] == ["1AC"]
    await client.patch(f"/api/v1/packs/{by_level[0]['id']}", json={"is_active": False})
    active = (await client.get("/api/v1/packs", params={"active": True})).json()
    assert [p["level"] for p in active] == ["2BAC"]


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #


async def test_delete_unused_pack(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "1AC"})).json()[0]["id"]
    assert (await client.delete(f"/api/v1/packs/{pack_id}")).status_code == 204


async def test_delete_pack_with_students_is_409(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    _student(db_session, pack_id=pack_id)
    resp = await client.delete(f"/api/v1/packs/{pack_id}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "pack_in_use"


# --------------------------------------------------------------------------- #
# a student's pack and price
# --------------------------------------------------------------------------- #


async def test_enrol_onto_a_pack(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    resp = await client.post(
        "/api/v1/students", json={"first_name": "Amina", "join_date": _JOIN, "pack_id": pack_id}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pack"] == {
        "id": pack_id,
        "name": "Maths seul",
        "level": "2BAC",
        "price": "150.00",
    }
    assert body["custom_price"] is None


async def test_enrol_with_an_agreed_price(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    resp = await client.post(
        "/api/v1/students",
        json={
            "first_name": "Sara",
            "join_date": _JOIN,
            "pack_id": pack_id,
            "custom_price": "90",
            "price_note": "remise fratrie",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["custom_price"] == "90.00"
    assert resp.json()["price_note"] == "remise fratrie"


async def test_enrol_onto_an_unknown_pack_is_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students", json={"first_name": "X", "join_date": _JOIN, "pack_id": 999}
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "pack_not_found"


async def test_enrol_onto_a_retired_pack_is_400(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    await client.patch(f"/api/v1/packs/{pack_id}", json={"is_active": False})
    resp = await client.post(
        "/api/v1/students", json={"first_name": "X", "join_date": _JOIN, "pack_id": pack_id}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "pack_inactive"


async def test_student_payload_carries_price_and_amount_owed(
    client: AsyncClient, db_session: Session
) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    student = _student(db_session, pack_id=pack_id)
    detail = (
        await client.get(f"/api/v1/students/{student.id}", params={"as_of": "2023-06-30"})
    ).json()
    assert detail["monthly_price"] == "150.00"
    assert detail["months_overdue"] == 4
    assert detail["amount_owed"] == "600.00"


async def test_patching_the_pack_changes_the_price(
    client: AsyncClient, db_session: Session
) -> None:
    _offering(db_session)
    packs = (await client.get("/api/v1/packs")).json()
    student = _student(db_session, pack_id=packs[0]["id"])
    resp = await client.patch(f"/api/v1/students/{student.id}", json={"pack_id": packs[1]["id"]})
    assert resp.status_code == 200
    assert resp.json()["pack"]["id"] == packs[1]["id"]


async def test_clearing_the_agreed_price_returns_them_to_the_pack_price(
    client: AsyncClient, db_session: Session
) -> None:
    _offering(db_session)
    pack_id = (await client.get("/api/v1/packs", params={"level": "2BAC"})).json()[0]["id"]
    student = _student(db_session, pack_id=pack_id, custom_price=Decimal("90"))
    resp = await client.patch(f"/api/v1/students/{student.id}", json={"custom_price": None})
    assert resp.json()["custom_price"] is None
    detail = (await client.get(f"/api/v1/students/{student.id}")).json()
    assert detail["monthly_price"] == "150.00"


async def test_error_detail_is_localized(client: AsyncClient, db_session: Session) -> None:
    _offering(db_session)
    resp = await client.post(
        "/api/v1/packs",
        json={"name": "Maths seul", "level": "2BAC", "price": "9", "subjects": ["Maths"]},
        headers={"Accept-Language": "fr"},
    )
    assert "existe" in resp.json()["detail"].lower()


async def test_one_pack_is_edited_on_its_own(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/packs",
        json={"name": "Pack", "level": "TC", "price": "400", "subjects": ["Maths", "Physique"]},
    )
    pack_id = created.json()["id"]
    resp = await client.patch(
        f"/api/v1/packs/{pack_id}",
        json={
            "name": "Pack TC Scientifique",
            "level": "1BAC",
            "subjects": ["Maths"],
            "price": "420",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["name"], body["level"], body["subjects"], body["price"]) == (
        "Pack TC Scientifique",
        "1BAC",
        ["Maths"],
        "420.00",
    )


async def test_a_pack_with_students_keeps_its_level(
    client: AsyncClient, db_session: Session
) -> None:
    created = await client.post(
        "/api/v1/packs", json={"name": "Pack", "level": "TC", "price": "400", "subjects": ["Maths"]}
    )
    pack_id = created.json()["id"]
    _student(db_session, pack_id=pack_id)
    resp = await client.patch(
        f"/api/v1/packs/{pack_id}", json={"level": "1BAC"}, headers={"Accept-Language": "fr"}
    )
    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "1 élève(s) ont ce pack : son niveau ne peut plus changer",
        "code": "pack_level_locked",
    }
