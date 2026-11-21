"""Write endpoints: validation (422), domain errors (404/409/400), the full happy path,
and CLI<->API parity, through the signed-in `client`."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import AsyncClient
from typer.testing import CliRunner

from alembic import command
from app.cli import app as cli_app
from app.core import db as db_module
from app.core.provisioning import provision_tenant
from app.core.settings import settings
from app.models import User

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


async def _create_student(
    client: AsyncClient, name: str = "Amina", join: str = "2023-03-05", price: str = "300"
) -> int:
    resp = await client.post(
        "/api/v1/students",
        json={"first_name": name, "join_date": join, "custom_price": price},
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


# --------------------------------------------------------------------------- #
# Students: create / patch
# --------------------------------------------------------------------------- #


async def test_create_student(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/students",
        json={
            "first_name": "Amina",
            "join_date": "2023-03-05",
            "custom_price": "300",
            "phone": "+2126",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["full_name"] == "Amina"
    assert (await client.get(f"/api/v1/students/{data['id']}")).status_code == 200


async def test_patch_student(client: AsyncClient) -> None:
    sid = await _create_student(client)
    resp = await client.patch(
        f"/api/v1/students/{sid}",
        json={"phone": "+999", "custom_price": "350", "status": "inactive"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["phone"] == "+999"
    assert Decimal(str(data["custom_price"])) == Decimal("350")
    assert data["status"] == "inactive"
    assert data["join_date"] == "2023-03-05"  # anchor untouched


async def test_patch_partial_leaves_other_fields(client: AsyncClient) -> None:
    sid = await _create_student(client, price="300")
    # Only phone -> price and status unchanged.
    phone_only = await client.patch(f"/api/v1/students/{sid}", json={"phone": "+111"})
    assert phone_only.status_code == 200
    assert phone_only.json()["phone"] == "+111"
    assert Decimal(str(phone_only.json()["custom_price"])) == Decimal("300")
    assert phone_only.json()["status"] == "active"
    # Only status -> phone and price unchanged.
    status_only = await client.patch(f"/api/v1/students/{sid}", json={"status": "inactive"})
    assert status_only.status_code == 200
    assert status_only.json()["status"] == "inactive"
    assert status_only.json()["phone"] == "+111"


async def test_patch_rejecting_join_date_is_422(client: AsyncClient) -> None:
    sid = await _create_student(client)
    resp = await client.patch(f"/api/v1/students/{sid}", json={"join_date": "2024-01-01"})
    assert resp.status_code == 422


async def test_patch_unknown_field_is_422(client: AsyncClient) -> None:
    sid = await _create_student(client)
    assert (await client.patch(f"/api/v1/students/{sid}", json={"bogus": 1})).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"first_name": "X", "join_date": "2023-03-05", "custom_price": "-1"},  # negative price
        # blank name
        {"first_name": "", "last_name": "  ", "join_date": "2023-03-05", "custom_price": "1"},
        {"join_date": "2023-03-05", "custom_price": "1"},  # missing name
    ],
)
async def test_create_student_validation_422(client: AsyncClient, body: dict) -> None:
    assert (await client.post("/api/v1/students", json=body)).status_code == 422


# --------------------------------------------------------------------------- #
# Payments
# --------------------------------------------------------------------------- #


async def test_record_payment_by_cycle_and_by_month(client: AsyncClient) -> None:
    sid = await _create_student(client)
    by_cycle = await client.post(
        f"/api/v1/students/{sid}/payments",
        json={"paid_date": "2023-04-10", "amount": "300", "cycle_number": 1},
    )
    assert by_cycle.status_code == 201
    assert by_cycle.json()["expected_due_date"] == "2023-04-05"
    assert by_cycle.json()["days_late"] == 5

    by_month = await client.post(
        f"/api/v1/students/{sid}/payments",
        json={"paid_date": "2023-05-10", "amount": "300", "for_month": "2023-05"},
    )
    assert by_month.status_code == 201
    assert by_month.json()["cycle_number"] == 2


async def test_duplicate_payment_is_409(client: AsyncClient) -> None:
    sid = await _create_student(client)
    body = {"paid_date": "2023-04-10", "amount": "300", "cycle_number": 1}
    assert (await client.post(f"/api/v1/students/{sid}/payments", json=body)).status_code == 201
    assert (await client.post(f"/api/v1/students/{sid}/payments", json=body)).status_code == 409


@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("en", "350.00 is more than this student's monthly price of 300.00"),
        ("fr", "Le montant (350,00) dépasse le tarif mensuel de l'élève (300,00)"),
    ],
)
async def test_payment_above_the_monthly_price_is_400_with_a_readable_reason(
    client: AsyncClient, lang: str, message: str
) -> None:
    # The web form shows `detail` as is, so it has to make sense to the teacher.
    sid = await _create_student(client, price="300")
    resp = await client.post(
        f"/api/v1/students/{sid}/payments?lang={lang}",
        json={"paid_date": "2023-04-10", "amount": "350", "cycle_number": 1},
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": message, "code": "payment_exceeds_price"}


@pytest.mark.parametrize(
    "body",
    [
        {"paid_date": "2999-01-01", "amount": "300", "cycle_number": 1},  # future
        {"paid_date": "2023-04-10", "amount": "0", "cycle_number": 1},  # amount <= 0
        {"paid_date": "2023-04-10", "amount": "300"},  # neither selector
        {"paid_date": "2023-04-10", "amount": "300", "cycle_number": 1, "for_month": "2023-04"},
        {"paid_date": "2023-04-10", "amount": "300", "for_month": "2023-13"},  # bad month
    ],
)
async def test_payment_validation_422(client: AsyncClient, body: dict) -> None:
    sid = await _create_student(client)
    assert (await client.post(f"/api/v1/students/{sid}/payments", json=body)).status_code == 422


# --------------------------------------------------------------------------- #
# Correcting a payment from the app
# --------------------------------------------------------------------------- #


async def _paid_april(client: AsyncClient, price: str = "300") -> int:
    sid = await _create_student(client, price=price)
    resp = await client.post(
        f"/api/v1/students/{sid}/payments",
        json={"paid_date": "2023-04-10", "amount": price, "for_month": "2023-04"},
    )
    assert resp.status_code == 201, resp.text
    return sid


async def test_a_mistyped_amount_is_corrected(client: AsyncClient) -> None:
    sid = await _paid_april(client)
    resp = await client.patch(f"/api/v1/students/{sid}/payments/1", json={"amount": "250"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["amount"]) == Decimal("250")
    # The date was not touched, so neither is the lateness.
    assert (body["paid_date"], body["days_late"]) == ("2023-04-10", 5)


async def test_a_mistyped_date_is_corrected_and_lateness_follows_it(client: AsyncClient) -> None:
    sid = await _paid_april(client)
    resp = await client.patch(
        f"/api/v1/students/{sid}/payments/1", json={"paid_date": "2023-04-05"}
    )
    assert resp.status_code == 200, resp.text
    # Due on the 5th, so paid on the 5th is on time; the due date itself never moves.
    assert (resp.json()["expected_due_date"], resp.json()["days_late"]) == ("2023-04-05", 0)
    drift = await client.get(f"/api/v1/students/{sid}/ledger", params={"as_of": "2023-04-30"})
    assert drift.json()["cumulative_drift"] == 0


async def test_a_correction_above_the_price_is_refused(client: AsyncClient) -> None:
    sid = await _paid_april(client)
    resp = await client.patch(f"/api/v1/students/{sid}/payments/1", json={"amount": "350"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "payment_exceeds_price"


@pytest.mark.parametrize(
    "body",
    [
        {},  # nothing to change
        {"amount": "0"},
        {"paid_date": "2999-01-01"},
        {"cycle_number": 2},  # moving a payment is delete + record, never an edit
    ],
)
async def test_a_bad_correction_is_422(client: AsyncClient, body: dict) -> None:
    sid = await _paid_april(client)
    resp = await client.patch(f"/api/v1/students/{sid}/payments/1", json=body)
    assert resp.status_code == 422


async def test_correcting_or_deleting_a_month_never_paid_is_404(client: AsyncClient) -> None:
    sid = await _paid_april(client)
    patch = await client.patch(f"/api/v1/students/{sid}/payments/2", json={"amount": "100"})
    assert patch.status_code == 404
    assert (await client.delete(f"/api/v1/students/{sid}/payments/2")).status_code == 404


async def test_deleting_a_payment_makes_the_month_owed_again(client: AsyncClient) -> None:
    sid = await _paid_april(client)
    assert (await client.delete(f"/api/v1/students/{sid}/payments/1")).status_code == 204
    ledger = await client.get(f"/api/v1/students/{sid}/ledger", params={"as_of": "2023-04-30"})
    april = next(e for e in ledger.json()["entries"] if e["cycle_number"] == 1)
    assert april["paid_date"] is None
    # And the month can be recorded again, which is how a payment moves to another month.
    again = await client.post(
        f"/api/v1/students/{sid}/payments",
        json={"paid_date": "2023-04-12", "amount": "300", "for_month": "2023-04"},
    )
    assert again.status_code == 201


async def test_payment_month_before_schedule_is_422(client: AsyncClient) -> None:
    sid = await _create_student(client)  # join 2023-03
    resp = await client.post(
        f"/api/v1/students/{sid}/payments",
        json={"paid_date": "2023-02-10", "amount": "300", "for_month": "2023-02"},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Overrides
# --------------------------------------------------------------------------- #


async def test_create_override(client: AsyncClient) -> None:
    sid = await _create_student(client)
    resp = await client.post(
        f"/api/v1/students/{sid}/overrides",
        json={"new_due_date": "2023-07-20", "reason": "agreed to shift"},
    )
    assert resp.status_code == 201
    assert resp.json()["new_due_date"] == "2023-07-20"


async def test_override_blank_reason_is_422(client: AsyncClient) -> None:
    sid = await _create_student(client)
    resp = await client.post(
        f"/api/v1/students/{sid}/overrides",
        json={"new_due_date": "2023-07-20", "reason": "   "},
    )
    assert resp.status_code == 422


async def test_override_before_join_is_400(client: AsyncClient) -> None:
    sid = await _create_student(client)  # join 2023-03-05
    resp = await client.post(
        f"/api/v1/students/{sid}/overrides",
        json={"new_due_date": "2023-02-01", "reason": "too early"},
    )
    assert resp.status_code == 400


async def test_writes_on_unknown_student_are_404(client: AsyncClient) -> None:
    assert (await client.patch("/api/v1/students/999", json={"phone": "1"})).status_code == 404
    assert (
        await client.post(
            "/api/v1/students/999/payments",
            json={"paid_date": "2023-04-10", "amount": "300", "cycle_number": 1},
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/students/999/overrides",
            json={"new_due_date": "2023-07-20", "reason": "x"},
        )
    ).status_code == 404


# --------------------------------------------------------------------------- #
# Full flow + CLI<->API parity
# --------------------------------------------------------------------------- #


async def test_full_flow_drift_15(client: AsyncClient) -> None:
    sid = await _create_student(client)
    for month in ("2023-04", "2023-05", "2023-06"):
        resp = await client.post(
            f"/api/v1/students/{sid}/payments",
            json={"paid_date": f"{month}-10", "amount": "300", "for_month": month},
        )
        assert resp.status_code == 201
    drift = await client.get(f"/api/v1/students/{sid}/ledger", params={"as_of": "2023-06-10"})
    assert drift.json()["cumulative_drift"] == 15


async def test_cli_and_api_agree(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --- Same flow through the API (in-memory test DB) ---
    sid = await _create_student(client)
    for month in ("2023-04", "2023-05", "2023-06"):
        await client.post(
            f"/api/v1/students/{sid}/payments",
            json={"paid_date": f"{month}-10", "amount": "300", "for_month": month},
        )
    api_drift = (
        await client.get(f"/api/v1/students/{sid}/ledger", params={"as_of": "2023-06-30"})
    ).json()["cumulative_drift"]

    # --- Same flow through the CLI (separate temp-file DB) ---
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'cli.db'}")
    db_module.clear_engine_cache()
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")

    # The CLI works on one teacher's database, so it needs an account to work on. Inserted
    # directly rather than via AuthService to skip argon2 for a password nothing verifies here.
    with db_module.get_sessionmaker()() as session:
        user = User(username="cli", display_name="CLI", password_hash="unused", is_active=True)
        session.add(user)
        session.commit()
        provision_tenant(user.id)
    monkeypatch.setenv("ARDOISE_USER", "cli")

    runner = CliRunner()
    runner.invoke(
        cli_app,
        ["students", "add", "--first-name", "Amina", "--join-date", "2023-03-05", "--price", "300"],
    )
    for month in ("2023-04", "2023-05", "2023-06"):
        runner.invoke(
            cli_app,
            [
                "payments",
                "record",
                "1",
                "--date",
                f"{month}-10",
                "--amount",
                "300",
                "--for-month",
                month,
            ],
        )
    show = runner.invoke(cli_app, ["students", "show", "1", "--as-of", "2023-06-30"])
    db_module.clear_engine_cache()

    match = re.search(r"Cumulative drift:\s*(\d+)", show.output)
    assert match is not None, show.output
    cli_drift = int(match.group(1))

    assert api_drift == cli_drift == 15


async def test_the_list_and_the_student_say_how_late_they_usually_pay(client: AsyncClient) -> None:
    sid = await _create_student(client)  # joins 5 March 2023, 300 a month
    for month, day in (("2023-04", "10"), ("2023-05", "05"), ("2023-06", "12")):
        await client.post(
            f"/api/v1/students/{sid}/payments",
            json={"paid_date": f"{month}-{day}", "amount": "300", "for_month": month},
        )
    as_of = {"as_of": "2023-06-30"}
    # 5, 0 and 7 days late: 4 on average.
    detail = (await client.get(f"/api/v1/students/{sid}", params=as_of)).json()
    assert detail["average_days_late"] == 4
    row = (await client.get("/api/v1/students", params=as_of)).json()[0]
    assert row["average_days_late"] == 4

    fresh = await _create_student(client, name="Nouveau", join="2023-06-20")
    rows = (await client.get("/api/v1/students", params=as_of)).json()
    assert next(r for r in rows if r["id"] == fresh)["average_days_late"] is None
