"""The privacy guarantee, proven end-to-end against real database files.

Every other API test runs with `get_db` and `get_auth_db` both pointed at one in-memory database
(see `conftest._override_db`), which is convenient but means those tests *cannot* observe the
separation — they would pass just as happily if it didn't exist. So this module builds the real
thing: a central accounts database and two tenant files on disk, with no dependency overrides at
all, and drives it through HTTP.

If per-teacher privacy ever regresses, this is the file that fails.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import db as db_module
from app.core.db import tenant_url
from app.core.provisioning import migrate, provision_tenant
from app.core.settings import settings
from app.main import app as fastapi_app
from app.services.auth_service import AuthService

PASSWORD = "correct-horse"


@pytest.fixture
def two_teachers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    """A real central database on disk, two accounts, and a real database file for each."""
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'central.db'}")
    db_module.clear_engine_cache()
    migrate(db_module.central_url())

    ids: dict[str, int] = {}
    with db_module.get_sessionmaker()() as session:
        service = AuthService(session)
        for username in ("aymen", "ayoub"):
            user = service.create_user(
                username=username, display_name=username.title(), password=PASSWORD
            )
            ids[username] = user.id
            provision_tenant(user.id)

    yield ids
    db_module.clear_engine_cache()


async def _signed_in(username: str) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        yield client


async def _enrol(client: AsyncClient, first_name: str) -> int:
    response = await client.post(
        "/api/v1/students", json={"first_name": first_name, "join_date": "2026-01-05"}
    )
    assert response.status_code in (200, 201), response.text
    return int(response.json()["id"])


async def test_each_teacher_has_their_own_database_file(two_teachers: dict[str, int]) -> None:
    aymen, ayoub = tenant_url(two_teachers["aymen"]), tenant_url(two_teachers["ayoub"])
    assert aymen != ayoub
    assert Path(aymen.removeprefix("sqlite:///")).exists()
    assert Path(ayoub.removeprefix("sqlite:///")).exists()


async def test_one_teachers_students_are_invisible_to_the_other(
    two_teachers: dict[str, int],
) -> None:
    """The whole point of the feature."""
    async for aymen in _signed_in("aymen"):
        await _enrol(aymen, "Amina")
        mine = (await aymen.get("/api/v1/students")).json()
        assert [s["first_name"] for s in mine] == ["Amina"]

    async for ayoub in _signed_in("ayoub"):
        theirs = (await ayoub.get("/api/v1/students")).json()
        assert theirs == []


async def test_a_student_id_from_one_teacher_404s_for_the_other(
    two_teachers: dict[str, int],
) -> None:
    """Guessing an id must not be a way around the separation — and it isn't, because the row is
    not in the database being queried at all."""
    student_id = 0
    async for aymen in _signed_in("aymen"):
        student_id = await _enrol(aymen, "Amina")

    async for ayoub in _signed_in("ayoub"):
        assert (await ayoub.get(f"/api/v1/students/{student_id}")).status_code == 404


async def test_both_teachers_can_use_the_same_class_name(two_teachers: dict[str, int]) -> None:
    """`uq_school_class_level_name` is per-database, so "2BAC / A" is free for each of them.

    Under a shared table with an owner_id column this is exactly where it would have gone wrong:
    the second teacher would be told their class already exists, naming one they cannot see.
    """
    for username in ("aymen", "ayoub"):
        async for client in _signed_in(username):
            response = await client.post(
                "/api/v1/classes", json={"level": "2BAC", "name": "A"}
            )
            assert response.status_code in (200, 201), f"{username}: {response.text}"


async def test_both_teachers_can_use_the_same_pack_name(two_teachers: dict[str, int]) -> None:
    """Same reasoning for `uq_pack_name_level` — both will plausibly sell a "Pack Maths"."""
    for username in ("aymen", "ayoub"):
        async for client in _signed_in(username):
            response = await client.post(
                "/api/v1/packs",
                json={
                    "name": "Pack Maths",
                    "level": "2BAC",
                    "price": "300.00",
                    "subjects": ["Maths"],
                },
            )
            assert response.status_code in (200, 201), f"{username}: {response.text}"


async def test_writes_land_in_the_writers_database(two_teachers: dict[str, int]) -> None:
    """Both enrol someone; each sees exactly one student, and it is their own."""
    async for aymen in _signed_in("aymen"):
        await _enrol(aymen, "Amina")
    async for ayoub in _signed_in("ayoub"):
        await _enrol(ayoub, "Youssef")

    async for aymen in _signed_in("aymen"):
        assert [s["first_name"] for s in (await aymen.get("/api/v1/students")).json()] == ["Amina"]
    async for ayoub in _signed_in("ayoub"):
        assert [s["first_name"] for s in (await ayoub.get("/api/v1/students")).json()] == [
            "Youssef"
        ]


async def test_the_dashboard_and_reports_are_scoped_too(two_teachers: dict[str, int]) -> None:
    """These read through repos rather than their own queries, so they inherit the scoping — this
    pins that it stays true."""
    async for aymen in _signed_in("aymen"):
        await _enrol(aymen, "Amina")

    async for ayoub in _signed_in("ayoub"):
        summary = (await ayoub.get("/api/v1/dashboard/summary")).json()
        assert summary["active_students"] == 0
        assert summary["top_debtors"] == []
        assert summary["unbilled_students"] == []

        report = (
            await ayoub.get("/api/v1/reports/monthly", params={"year": 2026, "month": 1})
        ).json()
        assert report["rows"] == []
