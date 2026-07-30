"""Thin CRUD access for :class:`Student`. No business logic, no date math."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, StudentStatus


class StudentRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, student: Student) -> Student:
        self.session.add(student)
        self.session.flush()
        return student

    def get(self, student_id: int) -> Student | None:
        return self.session.get(Student, student_id)

    def list(self, *, status: StudentStatus | None = None) -> list[Student]:
        stmt = select(Student).order_by(Student.id)
        if status is not None:
            stmt = stmt.where(Student.status == status)
        return list(self.session.scalars(stmt))

    def delete(self, student: Student) -> None:
        self.session.delete(student)
        self.session.flush()
