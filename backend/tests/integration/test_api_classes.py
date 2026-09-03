"""API tests for classes — CRUD, the roster PDF, and the students-by-class filter."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.class_service import ClassService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_FEE = Decimal("300")
_AS_OF = {"as_of": "2023-04-30"}


def _seed(db_session: Session) -> tuple[int, int]:
    """One 2BAC class holding a student who paid cycle 1 five days late, plus an empty 1AC class."""
    classes = ClassService(db_session)
    bac = classes.create(level=ClassLevel.BAC2, name="Groupe A")
    ac = classes.create(level=ClassLevel.AC1, name="Groupe B")
    student = StudentService(db_session).enroll(
        first_name="Amina", phone="+212600000000", join_date=date(2023, 3, 5), custom_price=_FEE,
        class_id=bac.id,
    )
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    return bac.id, ac.id


# --------------------------------------------------------------------------- #
# list / create
# --------------------------------------------------------------------------- #


async def test_list_classes_in_school_order(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/classes", params=_AS_OF)
    assert resp.status_code == 200
    assert [(c["level"], c["name"]) for c in resp.json()] == [
        ("1AC", "Groupe B"),
        ("2BAC", "Groupe A"),
    ]


async def test_list_classes_carries_counts_and_drift(
    client: AsyncClient, db_session: Session
) -> None:
    bac_id, _ = _seed(db_session)
    data = (await client.get("/api/v1/classes", params=_AS_OF)).json()
    bac = next(c for c in data if c["id"] == bac_id)
    assert bac["student_count"] == 1
    assert bac["cumulative_drift"] == 5


async def test_list_classes_filters_by_level(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.get("/api/v1/classes", params={"level": "2BAC", **_AS_OF})
    assert [c["name"] for c in resp.json()] == ["Groupe A"]


async def test_create_class(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/classes", json={"level": "3AC", "name": "Groupe C"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["level"] == "3AC"
    assert body["name"] == "Groupe C"
    assert body["id"] is not None


async def test_create_duplicate_returns_409(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.post("/api/v1/classes", json={"level": "2BAC", "name": "Groupe A"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "duplicate_class"


async def test_create_blank_name_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/classes", json={"level": "3AC", "name": "   "})
    assert resp.status_code == 422


async def test_create_unknown_level_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/classes", json={"level": "6BAC", "name": "X"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# read / update / delete
# --------------------------------------------------------------------------- #


async def test_get_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.get(f"/api/v1/classes/{bac_id}", params=_AS_OF)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Groupe A"
    assert body["student_count"] == 1
    assert body["cumulative_drift"] == 5
    assert body["as_of"] == "2023-04-30"


async def test_get_unknown_class_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/classes/999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "class_not_found"


async def test_patch_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.patch(f"/api/v1/classes/{bac_id}", json={"name": "Groupe Z"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Groupe Z"


async def test_patch_collision_returns_409(client: AsyncClient, db_session: Session) -> None:
    bac_id, ac_id = _seed(db_session)
    resp = await client.patch(
        f"/api/v1/classes/{ac_id}", json={"level": "2BAC", "name": "Groupe A"}
    )
    assert resp.status_code == 409


async def test_patch_rejects_unknown_fields(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.patch(f"/api/v1/classes/{bac_id}", json={"nope": 1})
    assert resp.status_code == 422


async def test_delete_empty_class(client: AsyncClient, db_session: Session) -> None:
    _, ac_id = _seed(db_session)
    assert (await client.delete(f"/api/v1/classes/{ac_id}")).status_code == 204
    assert (await client.get(f"/api/v1/classes/{ac_id}")).status_code == 404


async def test_delete_non_empty_class_returns_409(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.delete(f"/api/v1/classes/{bac_id}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "class_not_empty"


# --------------------------------------------------------------------------- #
# roster PDF
# --------------------------------------------------------------------------- #


async def test_roster_pdf(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.get(f"/api/v1/classes/{bac_id}/roster.pdf", params=_AS_OF)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "2bac-groupe-a-roster.pdf" in resp.headers["content-disposition"]


async def test_roster_pdf_unknown_class_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/classes/999/roster.pdf")).status_code == 404


# --------------------------------------------------------------------------- #
# students <-> classes
# --------------------------------------------------------------------------- #


async def test_students_filter_by_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, ac_id = _seed(db_session)
    StudentService(db_session).enroll(
        first_name="Outsider", phone=None, join_date=date(2023, 3, 5), custom_price=_FEE
    )
    resp = await client.get("/api/v1/students", params={"class_id": bac_id, **_AS_OF})
    assert [s["full_name"] for s in resp.json()] == ["Amina"]
    assert (await client.get("/api/v1/students", params={"class_id": ac_id, **_AS_OF})).json() == []


async def test_student_payload_carries_its_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    body = (await client.get("/api/v1/students", params=_AS_OF)).json()[0]
    assert body["class_id"] == bac_id
    assert body["school_class"] == {"id": bac_id, "level": "2BAC", "name": "Groupe A"}


async def test_create_student_into_a_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, _ = _seed(db_session)
    resp = await client.post(
        "/api/v1/students",
        json={
            "first_name": "Nouveau",
            "join_date": "2023-03-05",
            "custom_price": "300",
            "class_id": bac_id,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["class_id"] == bac_id


async def test_create_student_into_unknown_class_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students",
        json={"first_name": "X", "join_date": "2023-03-05", "custom_price": "300", "class_id": 999},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "class_not_found"


async def test_patch_student_class(client: AsyncClient, db_session: Session) -> None:
    bac_id, ac_id = _seed(db_session)
    student_id = (await client.get("/api/v1/students", params=_AS_OF)).json()[0]["id"]
    assert (
        await client.patch(f"/api/v1/students/{student_id}", json={"class_id": ac_id})
    ).json()["class_id"] == ac_id
    # ...and unassigning is explicit null, not omission
    resp = await client.patch(f"/api/v1/students/{student_id}", json={"class_id": None})
    assert resp.json()["class_id"] is None
    assert resp.json()["school_class"] is None


async def test_patch_student_class_does_not_move_drift(
    client: AsyncClient, db_session: Session
) -> None:
    bac_id, ac_id = _seed(db_session)
    before = (await client.get("/api/v1/students", params=_AS_OF)).json()[0]
    await client.patch(f"/api/v1/students/{before['id']}", json={"class_id": ac_id})
    after = (await client.get(f"/api/v1/students/{before['id']}", params=_AS_OF)).json()
    assert after["cumulative_drift"] == before["cumulative_drift"] == 5


async def test_error_detail_is_localized(client: AsyncClient, db_session: Session) -> None:
    _seed(db_session)
    resp = await client.post(
        "/api/v1/classes",
        json={"level": "2BAC", "name": "Groupe A"},
        headers={"Accept-Language": "fr"},
    )
    assert resp.status_code == 409
    assert "existe" in resp.json()["detail"].lower()
