"""Leavers with debt — who walked away owing money.

A separate router rather than ``/students/...`` so the collection route can't collide with
``/students/{student_id}``: FastAPI would try to parse "leavers" as an int and 422.

Nothing here blocks anything. Re-admitting a student who owes is the teacher's decision; these
endpoints exist so that decision is an informed one.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.debt import DebtStatusOut, LeaversOut, WriteoffCreate, WriteoffOut
from app.schemas.student import StudentOut
from app.services.debt_service import DebtService, DebtStatus

router = APIRouter(prefix="/debts", tags=["debts"])


def _out(status: DebtStatus) -> DebtStatusOut:
    return DebtStatusOut(
        student=StudentOut.model_validate(status.student),
        left_on=status.left_on,
        amount_owed=status.amount_owed,
        months_owed=status.months_owed,
        left_with_debt=status.left_with_debt,
        written_off=(
            WriteoffOut.model_validate(status.written_off) if status.written_off else None
        ),
    )


@router.get("", response_model=LeaversOut)
async def list_leavers(db: Session = Depends(get_db)) -> LeaversOut:
    """Students who left owing money, largest debt first."""
    service = DebtService(db)
    return LeaversOut(
        leavers=[_out(status) for status in service.leavers_with_debt()],
        total_owed=service.total_owed(),
    )


@router.get("/matches", response_model=list[DebtStatusOut])
async def find_matches(
    db: Session = Depends(get_db),
    phone: str | None = Query(None),
    first_name: str | None = Query(None),
    last_name: str | None = Query(None),
) -> list[DebtStatusOut]:
    """Past leavers who still owe and match this phone or name.

    Called by the enrolment form so re-enrolling a debtor under a fresh record surfaces a warning.
    Advisory only — real people share names.
    """
    matches = DebtService(db).similar_leavers(
        phone=phone, first_name=first_name, last_name=last_name
    )
    return [_out(status) for status in matches]


@router.get("/{student_id}", response_model=DebtStatusOut)
async def get_debt(student_id: int, db: Session = Depends(get_db)) -> DebtStatusOut:
    return _out(DebtService(db).status(student_id))


@router.post("/{student_id}/write-off", response_model=WriteoffOut)
async def write_off(
    student_id: int, payload: WriteoffCreate, db: Session = Depends(get_db)
) -> WriteoffOut:
    """Forgive what a departed student owed, with a reason, on the record.

    Deliberately not a payment: it must never appear in collected revenue.
    """
    return WriteoffOut.model_validate(DebtService(db).write_off(student_id, reason=payload.reason))
