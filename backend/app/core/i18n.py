"""Tiny dependency-free i18n for the backend (English + French).

Right-sized for a single-teacher tool: a flat message catalog and two helpers, no gettext/babel.
The **service layer never translates** — it raises structured error *codes*; only the presentation
edges (API error handler, CSV exports, CLI) call :func:`translate`. English is the dev default,
French is for the teacher. A request picks a locale via ``Accept-Language`` or ``?lang=``
(see ``app/api/deps.py``).
"""

from app.core.settings import settings

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "fr")

# key -> {locale: template}. Templates use str.format params. French is written to read naturally
# for the teacher, not as a literal word-for-word translation.
MESSAGES: dict[str, dict[str, str]] = {
    # --- Domain error messages (keyed by exception code) ---
    "error.student_not_found": {
        "en": "No student with id {student_id}",
        "fr": "Aucun élève avec l'identifiant {student_id}",
    },
    "error.duplicate_payment": {
        "en": "Student {student_id} already has a payment for cycle {cycle_number}",
        "fr": "L'élève {student_id} a déjà un paiement pour le cycle {cycle_number}",
    },
    "error.override_reason_empty": {
        "en": "Override reason must not be empty",
        "fr": "Le motif du changement de date ne doit pas être vide",
    },
    "error.override_before_join": {
        "en": "Override date must be after the student's join date",
        "fr": "La date de changement doit être postérieure à la date d'inscription de l'élève",
    },
    "error.override_backwards": {
        "en": "Override date cannot be earlier than an existing override",
        "fr": "La date de changement ne peut pas être antérieure à un changement existant",
    },
    # --- Student status labels (used in CSV display) ---
    "status.active": {"en": "Active", "fr": "Actif"},
    "status.inactive": {"en": "Inactive", "fr": "Inactif"},
    # --- Ledger CSV headers + status column ---
    "csv.ledger.cycle": {"en": "Cycle", "fr": "Cycle"},
    "csv.ledger.due_date": {"en": "Due date", "fr": "Date d'échéance"},
    "csv.ledger.paid_date": {"en": "Paid date", "fr": "Date de paiement"},
    "csv.ledger.days_late": {"en": "Days late", "fr": "Jours de retard"},
    "csv.ledger.amount": {"en": "Amount", "fr": "Montant"},
    "csv.ledger.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.ledger.status": {"en": "Status", "fr": "Statut"},
    "csv.ledger.status.unpaid": {"en": "Unpaid", "fr": "Impayé"},
    "csv.ledger.status.on_time": {"en": "On time", "fr": "À temps"},
    "csv.ledger.status.days_late": {"en": "{days} days late", "fr": "En retard de {days} jours"},
    # --- Monthly report CSV headers ---
    "csv.monthly.student_id": {"en": "Student ID", "fr": "Identifiant élève"},
    "csv.monthly.name": {"en": "Name", "fr": "Nom"},
    "csv.monthly.status": {"en": "Status", "fr": "Statut"},
    "csv.monthly.fee": {"en": "Fee", "fr": "Frais"},
    "csv.monthly.collected": {"en": "Collected", "fr": "Encaissé"},
    "csv.monthly.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.monthly.outstanding": {"en": "Outstanding", "fr": "Solde dû"},
    # --- PDF export titles (the csv.* header/status keys above are reused for the table cells) ---
    "pdf.ledger.title": {"en": "Payment ledger", "fr": "Historique des paiements"},
    "pdf.monthly.title": {
        "en": "Monthly report — {month:02d}/{year}",
        "fr": "Rapport mensuel — {month:02d}/{year}",
    },
}


def normalize_locale(tag: str | None) -> str | None:
    """Map a language tag (``fr``, ``fr-FR``, ``EN``) to a supported locale, or ``None``."""
    if not tag:
        return None
    base = tag.strip().lower().split("-")[0]
    return base if base in SUPPORTED_LOCALES else None


def _default_locale() -> str:
    return (
        settings.default_locale if settings.default_locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    )


def resolve_locale(accept_language: str | None) -> str:
    """Pick the best supported locale from an ``Accept-Language`` header, else the default."""
    if accept_language:
        for part in accept_language.split(","):
            match = normalize_locale(part.split(";")[0])
            if match:
                return match
    return _default_locale()


def translate(key: str, locale: str, /, **params: object) -> str:
    """Render ``key`` in ``locale`` (falling back to the default locale, then the key itself)."""
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(locale) or entry.get(DEFAULT_LOCALE) or key
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template
