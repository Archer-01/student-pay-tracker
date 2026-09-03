"""API-level i18n: localized error messages via Accept-Language or ?lang.

(Export localization is covered as unit tests on the shaping helpers in
``tests/unit/test_export_tables.py`` — PDF byte streams aren't greppable for the localized text.)
"""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.services.student_service import StudentService


def _enroll(db_session: Session, name: str = "Amïra") -> int:
    return (
        StudentService(db_session)
        .enroll(
            first_name=name,
            phone=None,
            join_date=date(2023, 3, 5),
            custom_price=Decimal("300"),
        )
        .id
    )


async def test_error_default_is_english(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/students/999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "No student with id 999"
    assert body["code"] == "student_not_found"  # stable machine code for the frontend


async def test_error_french_via_accept_language(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/students/999", headers={"Accept-Language": "fr-FR,fr;q=0.9"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Aucun élève avec l'identifiant 999"
    assert body["code"] == "student_not_found"


async def test_error_french_via_lang_query_overrides_header(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/students/999", params={"lang": "fr"}, headers={"Accept-Language": "en"}
    )
    assert resp.json()["detail"] == "Aucun élève avec l'identifiant 999"


async def test_domain_error_localized(client: AsyncClient, db_session: Session) -> None:
    sid = _enroll(db_session)
    # Override before join date -> 400, in French.
    resp = await client.post(
        f"/api/v1/students/{sid}/overrides?lang=fr",
        json={"new_due_date": "2023-01-01", "reason": "trop tôt"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "override_before_join"
    assert "postérieure" in resp.json()["detail"]
