"""Tiny dependency-free i18n for the backend (English + French).

Right-sized for a single-teacher tool: a flat message catalog and two helpers, no gettext/babel.
The **service layer never translates** — it raises structured error *codes*; only the presentation
edges (API error handler, CSV exports, CLI) call :func:`translate`. English is the dev default,
French is for the teacher. A request picks a locale via ``Accept-Language`` or ``?lang=``
(see ``app/api/deps.py``).
"""

from datetime import date
from decimal import Decimal

from app.core.settings import settings

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "fr")

# key -> {locale: template}. Templates use str.format params. French is written to read naturally
# for the teacher, not as a literal word-for-word translation, and follows French typography: a
# no-break space (\u00a0) before : ; ? ! and inside « », so the punctuation never wraps onto a
# line of its own. tests/unit/test_i18n.py enforces it.
#
# A message that depends on a number comes as a pair, ``<key>_one`` / ``<key>_other``, picked by a
# ``count`` param (the i18next convention the frontend uses too). Call it by the bare key.
MESSAGES: dict[str, dict[str, str]] = {
    # --- Domain error messages (keyed by exception code) ---
    "error.student_not_found": {
        "en": "No student with id {student_id}",
        "fr": "Élève introuvable (n°\u00a0{student_id})",
    },
    "error.duplicate_payment": {
        "en": "A payment is already recorded for the month due {due_date}",
        "fr": "Un paiement est déjà enregistré pour l'échéance du {due_date}",
    },
    "error.payment_not_found": {
        "en": "No payment recorded for student {student_id}, cycle {cycle_number}",
        "fr": "Aucun paiement enregistré pour l'élève n°\u00a0{student_id}, cycle {cycle_number}",
    },
    "error.payment_amount_not_positive": {
        "en": "A payment amount must be more than zero",
        "fr": "Le montant doit être supérieur à zéro",
    },
    "error.payment_exceeds_price": {
        "en": "{amount} is more than this student's monthly price of {price}",
        "fr": "Le montant ({amount}) dépasse le tarif mensuel de l'élève ({price})",
    },
    "error.override_reason_empty": {
        "en": "Override reason must not be empty",
        "fr": "Indiquez le motif du décalage",
    },
    "error.override_before_join": {
        "en": "Override date must be after the student's join date",
        "fr": "La nouvelle échéance doit être postérieure à la date d'inscription de l'élève",
    },
    "error.override_backwards": {
        "en": "Override date cannot be earlier than an existing override",
        "fr": "La nouvelle échéance ne peut pas précéder un décalage déjà enregistré",
    },
    "error.class_not_found": {
        "en": "No class with id {class_id}",
        "fr": "Classe introuvable (n°\u00a0{class_id})",
    },
    "error.duplicate_class": {
        "en": "A {level} class named '{name}' already exists",
        "fr": "Une classe {level} nommée «\u00a0{name}\u00a0» existe déjà",
    },
    "error.class_not_empty": {
        "en": "Class {class_id} still has {student_count} student(s); unassign them first",
        "fr": "Cette classe compte encore {student_count} élève(s)\u00a0; retirez-les d'abord",
    },
    "error.class_name_empty": {
        "en": "Class name must not be empty",
        "fr": "Le nom de la classe est obligatoire",
    },
    "error.pack_not_found": {
        "en": "No pack with id {pack_id}",
        "fr": "Pack introuvable (n°\u00a0{pack_id})",
    },
    "error.duplicate_pack": {
        "en": "A pack named '{name}' already exists for {level}",
        "fr": "Un pack «\u00a0{name}\u00a0» existe déjà pour le niveau {level}",
    },
    "error.pack_in_use": {
        "en": "Pack {pack_id} is used by {student_count} student(s); deactivate it instead",
        "fr": (
            "Ce pack est attribué à {student_count} élève(s)\u00a0; "
            "désactivez-le plutôt que de le supprimer"
        ),
    },
    "error.pack_name_empty": {
        "en": "Pack name must not be empty",
        "fr": "Le nom du pack est obligatoire",
    },
    "error.pack_no_subjects": {
        "en": "A pack must contain at least one subject",
        "fr": "Un pack doit comporter au moins une matière",
    },
    "error.pack_no_prices": {
        "en": "At least one level price is required",
        "fr": "Indiquez un tarif pour au moins un niveau",
    },
    "error.pack_price_negative": {
        "en": "Pack price must not be negative",
        "fr": "Le tarif du pack ne peut pas être négatif",
    },
    "error.pack_offering_unknown": {
        "en": "No pack offering named '{name}'",
        "fr": "Aucune offre nommée «\u00a0{name}\u00a0»",
    },
    "error.pack_level_locked": {
        "en": "{student_count} student(s) are on this pack, so its level can no longer change",
        "fr": "{student_count} élève(s) ont ce pack\u00a0: son niveau ne peut plus changer",
    },
    "error.pack_inactive": {
        "en": "Pack {pack_id} is retired and cannot be assigned to a student",
        "fr": "Ce pack n'est plus proposé et ne peut pas être attribué à un élève",
    },
    "error.custom_price_negative": {
        "en": "Agreed price must not be negative",
        "fr": "Le tarif convenu ne peut pas être négatif",
    },
    # --- Sign-in / accounts (BACKLOG §5) ---
    # One message for wrong-username, wrong-password and deactivated alike: naming which one
    # failed would let an attacker enumerate accounts.
    "error.invalid_credentials": {
        "en": "Incorrect username or password",
        "fr": "Nom d'utilisateur ou mot de passe incorrect",
    },
    "error.too_many_attempts": {
        "en": "Too many failed sign-in attempts. Try again in {retry_after} seconds.",
        "fr": (
            "Trop de tentatives de connexion échouées. "
            "Réessayez dans {retry_after}\u00a0secondes."
        ),
    },
    "error.not_authenticated": {
        "en": "Please sign in to continue",
        "fr": "Veuillez vous connecter pour continuer",
    },
    "error.user_not_found": {
        "en": "No account named '{username}'",
        "fr": "Aucun compte nommé «\u00a0{username}\u00a0»",
    },
    "error.duplicate_user": {
        "en": "An account named '{username}' already exists",
        "fr": "Le compte «\u00a0{username}\u00a0» existe déjà",
    },
    "error.username_empty": {
        "en": "Username must not be empty",
        "fr": "Le nom d'utilisateur est obligatoire",
    },
    "error.display_name_empty": {
        "en": "Display name must not be empty",
        "fr": "Le nom affiché est obligatoire",
    },
    "error.password_too_short": {
        "en": "Password must be at least {minimum} characters",
        "fr": "Le mot de passe doit comporter au moins {minimum}\u00a0caractères",
    },
    # --- Enrollment periods (not attendance: long spans a student was enrolled) ---
    "error.period_not_open": {
        "en": "Student {student_id} has already left; there is no open period to close",
        "fr": "Cet élève est déjà parti\u00a0: aucune inscription en cours à clôturer",
    },
    "error.period_already_open": {
        "en": "Student {student_id} is already attending; record a departure first",
        "fr": "Cet élève est déjà inscrit\u00a0; indiquez d'abord son départ",
    },
    "error.leave_before_entry": {
        "en": "A departure ({leave_date}) cannot precede the arrival it closes ({entry_date})",
        "fr": (
            "La date de départ ({leave_date}) ne peut pas précéder "
            "la date d'arrivée ({entry_date})"
        ),
    },
    "error.return_before_leave": {
        "en": "A return ({entry_date}) cannot precede the last departure ({leave_date})",
        "fr": (
            "La date de retour ({entry_date}) ne peut pas précéder "
            "le dernier départ ({leave_date})"
        ),
    },
    "error.periods_overlap": {
        "en": "That change would make two attendance periods overlap",
        "fr": "Cette modification ferait se chevaucher deux périodes d'inscription",
    },
    "error.period_not_found": {
        "en": "No attendance period with id {period_id} for this student",
        "fr": "Période d'inscription introuvable (n°\u00a0{period_id})",
    },
    "error.first_entry_is_the_anchor": {
        "en": "The first arrival is the student's join date and cannot be moved",
        "fr": (
            "La première arrivée correspond à la date d'inscription de l'élève "
            "et ne peut pas être déplacée"
        ),
    },
    # --- Debts ("effacer la dette", not the accountant's "abandon de créance") ---
    "error.writeoff_reason_empty": {
        "en": "A write-off needs a reason",
        "fr": "Indiquez pourquoi la dette est effacée",
    },
    "error.nothing_to_write_off": {
        "en": "Student {student_id} has no outstanding balance to write off",
        "fr": "Cet élève n'a aucune dette à effacer",
    },
    "warning.returning_with_debt_one": {
        "en": "This student left owing {amount} for {count} month",
        "fr": "Cet élève est parti sans régler {amount} ({count}\u00a0mois)",
    },
    "warning.returning_with_debt_other": {
        "en": "This student left owing {amount} for {count} months",
        "fr": "Cet élève est parti sans régler {amount} ({count}\u00a0mois)",
    },
    # --- Ledger status for a month the student was away: not owed, so "not billed" ---
    "csv.ledger.status.away": {"en": "Away", "fr": "Non facturé"},
    # --- Student status labels (used in CSV display) ---
    "status.active": {"en": "Active", "fr": "Actif"},
    "status.inactive": {"en": "Inactive", "fr": "Inactif"},
    # --- Ledger headers + status column ---
    "csv.ledger.cycle": {"en": "Cycle", "fr": "N°"},
    "csv.ledger.due_date": {"en": "Due date", "fr": "Échéance"},
    "csv.ledger.paid_date": {"en": "Paid date", "fr": "Payé le"},
    "csv.ledger.days_late": {"en": "Days late", "fr": "Jours de retard"},
    "csv.ledger.amount": {"en": "Amount", "fr": "Montant"},
    "csv.ledger.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.ledger.status": {"en": "Status", "fr": "Statut"},
    "csv.ledger.status.unpaid": {"en": "Unpaid", "fr": "Impayé"},
    "csv.ledger.status.on_time": {"en": "On time", "fr": "À l'heure"},
    "csv.ledger.status.days_late_one": {
        "en": "{count} day late",
        "fr": "{count}\u00a0jour de retard",
    },
    "csv.ledger.status.days_late_other": {
        "en": "{count} days late",
        "fr": "{count}\u00a0jours de retard",
    },
    # --- Month names (the annual report's row labels) ---
    "month.1": {"en": "January", "fr": "Janvier"},
    "month.2": {"en": "February", "fr": "Février"},
    "month.3": {"en": "March", "fr": "Mars"},
    "month.4": {"en": "April", "fr": "Avril"},
    "month.5": {"en": "May", "fr": "Mai"},
    "month.6": {"en": "June", "fr": "Juin"},
    "month.7": {"en": "July", "fr": "Juillet"},
    "month.8": {"en": "August", "fr": "Août"},
    "month.9": {"en": "September", "fr": "Septembre"},
    "month.10": {"en": "October", "fr": "Octobre"},
    "month.11": {"en": "November", "fr": "Novembre"},
    "month.12": {"en": "December", "fr": "Décembre"},
    # --- Annual report ---
    "csv.annual.month": {"en": "Month", "fr": "Mois"},
    "csv.annual.collected": {"en": "Collected", "fr": "Encaissé"},
    "csv.annual.payments": {"en": "Payments", "fr": "Paiements"},
    "pdf.annual.title": {"en": "Annual revenue — {year}", "fr": "Bilan annuel — {year}"},
    "pdf.annual.empty": {
        "en": "No payments were recorded in this year.",
        "fr": "Aucun paiement enregistré cette année.",
    },
    "pdf.stat.best_month": {"en": "Best month", "fr": "Meilleur mois"},
    "pdf.stat.school_share": {
        "en": "School's share ({percent})",
        "fr": "Part de l'école ({percent})",
    },
    "pdf.stat.teacher_share": {"en": "Your share", "fr": "Votre part"},
    "pdf.stat.monthly_average": {"en": "Monthly average", "fr": "Moyenne mensuelle"},
    # --- Monthly report headers ---
    "csv.monthly.student_id": {"en": "Student ID", "fr": "N° élève"},
    "csv.monthly.name": {"en": "Name", "fr": "Nom"},
    "csv.monthly.status": {"en": "Status", "fr": "Statut"},
    "csv.monthly.price": {"en": "Price", "fr": "Tarif"},
    "csv.monthly.collected": {"en": "Collected", "fr": "Encaissé"},
    "csv.monthly.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.monthly.outstanding": {"en": "Outstanding", "fr": "Reste dû"},
    # --- Class roster export ---
    "csv.roster.student_id": {"en": "Student ID", "fr": "N° élève"},
    "csv.roster.name": {"en": "Name", "fr": "Nom"},
    "csv.roster.phone": {"en": "Phone", "fr": "Téléphone"},
    "csv.roster.status": {"en": "Status", "fr": "Statut"},
    "csv.roster.price": {"en": "Price", "fr": "Tarif"},
    "csv.roster.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.roster.months_overdue": {"en": "Months overdue", "fr": "Mois impayés"},
    "csv.roster.amount_owed": {"en": "Amount owed", "fr": "Montant dû"},
    # --- PDF export titles (the csv.* header/status keys above are reused for the table cells) ---
    "pdf.ledger.title": {"en": "Payment ledger", "fr": "Historique des paiements"},
    "pdf.ledger.empty": {
        "en": "No billing cycles have fallen due yet.",
        "fr": "Aucune échéance pour le moment.",
    },
    "pdf.roster.empty": {
        "en": "No students in this class yet.",
        "fr": "Aucun élève dans cette classe pour le moment.",
    },
    "pdf.monthly.empty": {
        "en": "No active students for this month.",
        "fr": "Aucun élève inscrit ce mois-ci.",
    },
    "pdf.footer": {
        "en": "Generated {generated} · figures as of {as_of}",
        "fr": "Généré le {generated} · chiffres au {as_of}",
    },
    # --- Shared labels for the PDF header blocks ---
    "pdf.field.phone": {"en": "Phone", "fr": "Téléphone"},
    "pdf.field.status": {"en": "Status", "fr": "Statut"},
    "pdf.field.join_date": {"en": "Student since", "fr": "Date d'inscription"},
    "pdf.field.first_payment": {"en": "First payment", "fr": "Premier paiement"},
    "pdf.field.repeating": {"en": "Repeating the year", "fr": "Redoublant"},
    "pdf.field.price_note": {"en": "Agreed price", "fr": "Tarif convenu"},
    "pdf.stat.monthly_price": {"en": "Monthly price", "fr": "Tarif mensuel"},
    "pdf.stat.total_paid": {"en": "Total paid", "fr": "Total payé"},
    "pdf.stat.months_overdue": {"en": "Months overdue", "fr": "Mois impayés"},
    "pdf.stat.amount_owed": {"en": "Amount owed", "fr": "Montant dû"},
    "pdf.stat.drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "pdf.stat.students": {"en": "Students", "fr": "Élèves"},
    "pdf.stat.collected": {"en": "Collected", "fr": "Encaissé"},
    "pdf.stat.outstanding": {"en": "Outstanding", "fr": "Impayés"},
    "pdf.value.yes": {"en": "Yes", "fr": "Oui"},
    "pdf.value.no": {"en": "No", "fr": "Non"},
    "pdf.value.none": {"en": "—", "fr": "—"},
    "pdf.value.days_one": {"en": "{count} day", "fr": "{count}\u00a0jour"},
    "pdf.value.days_other": {"en": "{count} days", "fr": "{count}\u00a0jours"},
    "pdf.value.unassigned": {"en": "Unassigned", "fr": "Sans classe"},
    "pdf.value.no_pack": {"en": "No pack", "fr": "Aucun pack"},
    "pdf.roster.title": {"en": "Class roster", "fr": "Liste de la classe"},
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


def format_date(value: date, locale: str) -> str:
    """A date as the teacher reads it: 26/10/2026 in French. English keeps ISO, as before."""
    return value.strftime("%d/%m/%Y") if locale == "fr" else value.isoformat()


def format_money(value: Decimal, locale: str) -> str:
    """An amount to the cent: ``1\u00a0234,50`` in French, ``1234.50`` in English (as before).

    Thousands are grouped with U+00A0, not the narrower U+202F French typesetting prefers: the
    PDFs draw with Helvetica in WinAnsi encoding, which has no U+202F.
    """
    if locale != "fr":
        return f"{value:.2f}"
    return f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")


def format_percent(value: Decimal, locale: str) -> str:
    """``25`` → "25 %" in French (no-break space), "25%" in English; "12,5 %" keeps its decimal."""
    text = format(value.normalize(), "f")
    if locale != "fr":
        return f"{text}%"
    return text.replace(".", ",") + "\u00a0%"


def _plural_form(locale: str, count: int) -> str:
    # French treats 0 as singular ("0 jour"); English does not ("0 days").
    if locale == "fr":
        return "one" if count in (0, 1) else "other"
    return "one" if count == 1 else "other"


def _localize(value: object, locale: str) -> object:
    """Render a date or an amount the way the locale writes it; leave everything else alone."""
    if isinstance(value, date):
        return format_date(value, locale)
    if isinstance(value, Decimal):
        return format_money(value, locale)
    return value


def translate(key: str, locale: str, /, **params: object) -> str:
    """Render ``key`` in ``locale`` (falling back to the default locale, then the key itself).

    Date and ``Decimal`` params are formatted for the locale, so callers pass the values
    themselves rather than pre-formatted strings.
    """
    count = params.get("count")
    if isinstance(count, int) and f"{key}_one" in MESSAGES:
        key = f"{key}_{_plural_form(locale, count)}"
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(locale) or entry.get(DEFAULT_LOCALE) or key
    try:
        return template.format(**{name: _localize(v, locale) for name, v in params.items()})
    except (KeyError, IndexError):
        return template
