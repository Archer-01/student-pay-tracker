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


class DuplicatePaymentError(DomainError):
    def __init__(self, student_id: int, cycle_number: int) -> None:
        super().__init__("duplicate_payment", student_id=student_id, cycle_number=cycle_number)


class InvalidOverrideError(DomainError):
    """Bad override. ``code`` is one of: override_reason_empty / override_before_join /
    override_backwards."""
