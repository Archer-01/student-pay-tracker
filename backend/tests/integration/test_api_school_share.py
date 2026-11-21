"""The school owner's share, as the API and the PDFs report it."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.settings import Settings, settings
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService
from tests.pdf import pdf_text


def _paid_in_october(db_session: Session) -> None:
    students = StudentService(db_session)
    amina = students.enroll(
        first_name="Amina", phone=None, join_date=date(2026, 9, 5), custom_price=Decimal("240")
    )
    PaymentService(db_session).record_payment(
        student_id=amina.id, cycle_number=1, paid_date=date(2026, 10, 5), amount=Decimal("240")
    )


async def test_month_year_and_home_report_the_same_split(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("25"))
    _paid_in_october(db_session)
    expected = {"percent": "25", "school": "60.00", "teacher": "180.00"}

    month = (await client.get("/api/v1/reports/monthly", params={"year": 2026, "month": 10})).json()
    year = (await client.get("/api/v1/reports/annual", params={"year": 2026})).json()
    home = (await client.get("/api/v1/dashboard/summary", params={"as_of": "2026-10-31"})).json()

    assert month["share"] == expected
    assert year["months"][9]["share"] == expected
    assert year["share"] == expected
    assert home["share_this_month"] == expected


async def test_at_zero_the_teacher_keeps_everything(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("0"))
    _paid_in_october(db_session)
    month = (await client.get("/api/v1/reports/monthly", params={"year": 2026, "month": 10})).json()
    assert month["share"] == {"percent": "0", "school": "0.00", "teacher": "240.00"}


@pytest.mark.parametrize("value", ["-1", "100.5", "abc"])
def test_the_setting_must_be_a_percentage(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHOOL_SHARE_PERCENT", value)
    with pytest.raises(ValidationError):
        Settings()


def test_the_setting_defaults_to_a_quarter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHOOL_SHARE_PERCENT", raising=False)
    assert Settings(_env_file=None).school_share_percent == Decimal("25")  # type: ignore[call-arg]


@pytest.mark.parametrize("kind", ["monthly", "annual"])
async def test_the_pdfs_show_both_parts_in_french(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("25"))
    _paid_in_october(db_session)
    params = (
        {"year": 2026, "month": 10, "lang": "fr"}
        if kind == "monthly"
        else {"year": 2026, "lang": "fr"}
    )
    text = pdf_text((await client.get(f"/api/v1/reports/{kind}.pdf", params=params)).content)
    assert "part de l'école (25 %)" in text
    assert "60 dh" in text and "180 dh" in text
    assert "votre part" in text


async def test_the_pdfs_say_nothing_about_a_share_of_zero(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("0"))
    _paid_in_october(db_session)
    params = {"year": 2026, "month": 10, "lang": "fr"}
    text = pdf_text((await client.get("/api/v1/reports/monthly.pdf", params=params)).content)
    assert "votre part" not in text


# --------------------------------------------------------------------------- #
# Handing the school its share
# --------------------------------------------------------------------------- #


async def test_a_month_is_marked_handed_over_and_unmarked(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("25"))
    _paid_in_october(db_session)
    months = (await client.get("/api/v1/school-share")).json()
    assert months["percent"] == "25"
    october = next(m for m in months["months"] if (m["year"], m["month"]) == (2026, 10))
    assert (october["due"], october["status"], october["remaining"]) == ("60.00", "due", "60.00")

    marked = await client.put("/api/v1/school-share/2026/10", json={"handed_on": "2026-11-03"})
    assert marked.status_code == 200, marked.text
    october = next(m for m in marked.json()["months"] if m["month"] == 10)
    assert (october["status"], october["handed_on"]) == ("handed", "2026-11-03")

    assert (await client.delete("/api/v1/school-share/2026/10")).status_code == 204
    assert (await client.delete("/api/v1/school-share/2026/10")).status_code == 404


async def test_a_handover_that_makes_no_sense_is_refused_in_words(
    client: AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("25"))
    _paid_in_october(db_session)
    resp = await client.put("/api/v1/school-share/2026/9?lang=fr", json={"handed_on": "2026-10-03"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "nothing_to_hand_over"
    assert resp.json()["detail"].startswith("Rien n'a été encaissé ce mois-là")
    bad = await client.put("/api/v1/school-share/2026/13", json={"handed_on": "2026-10-03"})
    assert bad.status_code == 422
