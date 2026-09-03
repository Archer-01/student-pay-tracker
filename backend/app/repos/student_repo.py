"""Thin CRUD access for :class:`Student`. No business logic, no date math."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

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

    def list(
        self,
        *,
        status: StudentStatus | None = None,
        class_id: int | None = None,
        query: str | None = None,
    ) -> list[Student]:
        # selectinload keeps the class available for list rendering in one extra query rather
        # than one per student.
        stmt = (
            select(Student)
            # Both are needed to render a student row (class label, effective price), so load
            # them in two extra queries rather than one per student.
            .options(selectinload(Student.school_class), selectinload(Student.pack))
            .order_by(Student.last_name, Student.first_name, Student.id)
        )
        if status is not None:
            stmt = stmt.where(Student.status == status)
        if class_id is not None:
            stmt = stmt.where(Student.class_id == class_id)
        if query:
            # Match either part, so searching "benali" or "amina" both find Amina Benali.
            like = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(Student.first_name.ilike(like), Student.last_name.ilike(like))
            )
        return list(self.session.scalars(stmt))

    def count_in_class(self, class_id: int) -> int:
        """How many students are assigned to a class (drives the "class not empty" rule)."""
        stmt = select(func.count()).select_from(Student).where(Student.class_id == class_id)
        return self.session.scalar(stmt) or 0

    def count_on_pack(self, pack_id: int) -> int:
        """How many students are on a pack (drives the "deactivate, don't delete" rule)."""
        stmt = select(func.count()).select_from(Student).where(Student.pack_id == pack_id)
        return self.session.scalar(stmt) or 0

    def delete(self, student: Student) -> None:
        self.session.delete(student)
        self.session.flush()
