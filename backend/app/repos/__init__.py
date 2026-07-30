"""Repositories — thin CRUD wrappers over the ORM models."""

from app.repos.override_repo import OverrideRepo
from app.repos.payment_repo import PaymentRepo
from app.repos.student_repo import StudentRepo

__all__ = ["OverrideRepo", "PaymentRepo", "StudentRepo"]
