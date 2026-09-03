"""Domain-level exceptions raised by the service layer.

Locale-agnostic: each error carries a stable machine ``code`` plus formatting ``params``, never a
pre-rendered sentence. The presentation edges (API handler, CLI) translate ``error.<code>`` via
``app.core.i18n`` — so the service layer knows nothing about English/French.
"""


class DomainError(Exception):
    """Base class: a stable ``code`` and template ``params`` for later localization."""

    def __init__(self, code: str, **params: object) -> None:
        self.code = code
        self.params = params
        super().__init__(code)


class StudentNotFoundError(DomainError):
    def __init__(self, student_id: int) -> None:
        super().__init__("student_not_found", student_id=student_id)


class InvalidPeriodError(DomainError):
    """Bad enrollment period. ``code`` is one of: period_not_open / period_already_open /
    leave_before_entry / return_before_leave / periods_overlap / period_not_found /
    first_entry_is_the_anchor."""


class InvalidWriteoffError(DomainError):
    """Bad debt write-off. ``code`` is one of: writeoff_reason_empty / nothing_to_write_off."""


class InvalidStudentError(DomainError):
    """Bad student data. ``code`` is one of: first_name_empty."""


class DuplicatePaymentError(DomainError):
    def __init__(self, student_id: int, cycle_number: int) -> None:
        super().__init__("duplicate_payment", student_id=student_id, cycle_number=cycle_number)


class InvalidOverrideError(DomainError):
    """Bad override. ``code`` is one of: override_reason_empty / override_before_join /
    override_backwards."""


class ClassNotFoundError(DomainError):
    def __init__(self, class_id: int) -> None:
        super().__init__("class_not_found", class_id=class_id)


class DuplicateClassError(DomainError):
    def __init__(self, level: str, name: str) -> None:
        super().__init__("duplicate_class", level=level, name=name)


class ClassNotEmptyError(DomainError):
    """Refuses to delete a class that still has students — unassign them first."""

    def __init__(self, class_id: int, student_count: int) -> None:
        super().__init__("class_not_empty", class_id=class_id, student_count=student_count)


class InvalidClassError(DomainError):
    """Bad class data. ``code`` is one of: class_name_empty."""


class PackNotFoundError(DomainError):
    def __init__(self, pack_id: int) -> None:
        super().__init__("pack_not_found", pack_id=pack_id)


class DuplicatePackError(DomainError):
    def __init__(self, name: str, level: str) -> None:
        super().__init__("duplicate_pack", name=name, level=level)


class PackInUseError(DomainError):
    """Refuses to delete a pack students are on — deactivate it instead."""

    def __init__(self, pack_id: int, student_count: int) -> None:
        super().__init__("pack_in_use", pack_id=pack_id, student_count=student_count)


class InvalidPackError(DomainError):
    """Bad pack data or pricing. ``code`` is one of: pack_name_empty / pack_no_subjects /
    pack_no_prices / pack_price_negative / pack_offering_unknown / pack_inactive /
    custom_price_negative."""
