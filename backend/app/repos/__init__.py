"""Repositories — thin CRUD wrappers over the ORM models."""

from app.repos.class_repo import ClassRepo
from app.repos.enrollment_repo import EnrollmentRepo
from app.repos.override_repo import OverrideRepo
from app.repos.pack_repo import PackRepo, SubjectRepo
from app.repos.payment_repo import PaymentRepo
from app.repos.student_repo import StudentRepo

__all__ = [
    "ClassRepo",
    "EnrollmentRepo",
    "OverrideRepo",
    "PackRepo",
    "PaymentRepo",
    "StudentRepo",
    "SubjectRepo",
]
