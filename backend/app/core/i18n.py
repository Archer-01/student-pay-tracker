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
    "error.class_not_found": {
        "en": "No class with id {class_id}",
        "fr": "Aucune classe avec l'identifiant {class_id}",
    },
    "error.duplicate_class": {
        "en": "A {level} class named '{name}' already exists",
        "fr": "Une classe {level} nommée « {name} » existe déjà",
    },
    "error.class_not_empty": {
        "en": "Class {class_id} still has {student_count} student(s); unassign them first",
        "fr": "La classe {class_id} compte encore {student_count} élève(s) ; retirez-les d'abord",
    },
    "error.class_name_empty": {
        "en": "Class name must not be empty",
        "fr": "Le nom de la classe ne doit pas être vide",
    },
    "error.pack_not_found": {
        "en": "No pack with id {pack_id}",
        "fr": "Aucun pack avec l'identifiant {pack_id}",
    },
    "error.duplicate_pack": {
        "en": "A pack named '{name}' already exists for {level}",
        "fr": "Un pack nommé « {name} » existe déjà pour {level}",
    },
    "error.pack_in_use": {
        "en": "Pack {pack_id} is used by {student_count} student(s); deactivate it instead",
        "fr": "Le pack {pack_id} est utilisé par {student_count} élève(s) ; désactivez-le plutôt",
    },
    "error.pack_name_empty": {
        "en": "Pack name must not be empty",
        "fr": "Le nom du pack ne doit pas être vide",
    },
    "error.pack_no_subjects": {
        "en": "A pack must contain at least one subject",
        "fr": "Un pack doit contenir au moins une matière",
    },
    "error.pack_no_prices": {
        "en": "At least one level price is required",
        "fr": "Au moins un tarif par niveau est requis",
    },
    "error.pack_price_negative": {
        "en": "Pack price must not be negative",
        "fr": "Le tarif du pack ne doit pas être négatif",
    },
    "error.pack_offering_unknown": {
        "en": "No pack offering named '{name}'",
        "fr": "Aucune offre de pack nommée « {name} »",
    },
    "error.pack_inactive": {
        "en": "Pack {pack_id} is retired and cannot be assigned to a student",
        "fr": "Le pack {pack_id} est retiré et ne peut pas être attribué à un élève",
    },
    "error.custom_price_negative": {
        "en": "Agreed price must not be negative",
        "fr": "Le tarif convenu ne doit pas être négatif",
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
        "fr": "Trop de tentatives de connexion échouées. Réessayez dans {retry_after} secondes.",
    },
    "error.not_authenticated": {
        "en": "Please sign in to continue",
        "fr": "Veuillez vous connecter pour continuer",
    },
    "error.user_not_found": {
        "en": "No account named '{username}'",
        "fr": "Aucun compte nommé « {username} »",
    },
    "error.duplicate_user": {
        "en": "An account named '{username}' already exists",
        "fr": "Un compte nommé « {username} » existe déjà",
    },
    "error.username_empty": {
        "en": "Username must not be empty",
        "fr": "Le nom d'utilisateur ne doit pas être vide",
    },
    "error.display_name_empty": {
        "en": "Display name must not be empty",
        "fr": "Le nom affiché ne doit pas être vide",
    },
    "error.password_too_short": {
        "en": "Password must be at least {minimum} characters",
        "fr": "Le mot de passe doit comporter au moins {minimum} caractères",
    },
    "error.period_not_open": {
        "en": "Student {student_id} has already left; there is no open period to close",
        "fr": "L'élève {student_id} est déjà parti ; aucune période ouverte à clôturer",
    },
    "error.period_already_open": {
        "en": "Student {student_id} is already attending; record a departure first",
        "fr": "L'élève {student_id} est déjà présent ; enregistrez d'abord un départ",
    },
    "error.leave_before_entry": {
        "en": "A departure ({leave_date}) cannot precede the arrival it closes ({entry_date})",
        "fr": (
            "Un départ ({leave_date}) ne peut pas précéder "
            "l'arrivée qu'il clôture ({entry_date})"
        ),
    },
    "error.return_before_leave": {
        "en": "A return ({entry_date}) cannot precede the last departure ({leave_date})",
        "fr": "Un retour ({entry_date}) ne peut pas précéder le dernier départ ({leave_date})",
    },
    "error.periods_overlap": {
        "en": "That change would make two attendance periods overlap",
        "fr": "Ce changement ferait se chevaucher deux périodes de présence",
    },
    "error.period_not_found": {
        "en": "No attendance period with id {period_id} for this student",
        "fr": "Aucune période de présence avec l'identifiant {period_id} pour cet élève",
    },
    "error.first_entry_is_the_anchor": {
        "en": "The first arrival is the student's join date and cannot be moved",
        "fr": (
            "La première arrivée est la date d'inscription de l'élève "
            "et ne peut pas être déplacée"
        ),
    },
    "error.writeoff_reason_empty": {
        "en": "A write-off needs a reason",
        "fr": "Un abandon de créance doit être motivé",
    },
    "error.nothing_to_write_off": {
        "en": "Student {student_id} has no outstanding balance to write off",
        "fr": "L'élève {student_id} n'a aucun solde à abandonner",
    },
    "warning.returning_with_debt": {
        "en": "This student left owing {amount} for {months} month(s)",
        "fr": "Cet élève est parti en devant {amount} pour {months} mois",
    },
    # --- Ledger status for a month the student was away ---
    "csv.ledger.status.away": {"en": "Away", "fr": "Absent"},
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
    "pdf.annual.title": {"en": "Annual revenue — {year}", "fr": "Revenus annuels — {year}"},
    "pdf.annual.empty": {
        "en": "No payments were recorded in this year.",
        "fr": "Aucun paiement enregistré cette année.",
    },
    "pdf.stat.best_month": {"en": "Best month", "fr": "Meilleur mois"},
    "pdf.stat.monthly_average": {"en": "Monthly average", "fr": "Moyenne mensuelle"},
    # --- Monthly report CSV headers ---
    "csv.monthly.student_id": {"en": "Student ID", "fr": "Identifiant élève"},
    "csv.monthly.name": {"en": "Name", "fr": "Nom"},
    "csv.monthly.status": {"en": "Status", "fr": "Statut"},
    "csv.monthly.price": {"en": "Price", "fr": "Tarif"},
    "csv.monthly.collected": {"en": "Collected", "fr": "Encaissé"},
    "csv.monthly.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.monthly.outstanding": {"en": "Outstanding", "fr": "Solde dû"},
    # --- Class roster export ---
    "csv.roster.student_id": {"en": "Student ID", "fr": "Identifiant élève"},
    "csv.roster.name": {"en": "Name", "fr": "Nom"},
    "csv.roster.phone": {"en": "Phone", "fr": "Téléphone"},
    "csv.roster.status": {"en": "Status", "fr": "Statut"},
    "csv.roster.price": {"en": "Price", "fr": "Tarif"},
    "csv.roster.cumulative_drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "csv.roster.months_overdue": {"en": "Months overdue", "fr": "Mois en retard"},
    "csv.roster.amount_owed": {"en": "Amount owed", "fr": "Montant dû"},
    # --- PDF export titles (the csv.* header/status keys above are reused for the table cells) ---
    "pdf.ledger.title": {"en": "Payment ledger", "fr": "Historique des paiements"},
    "pdf.ledger.empty": {
        "en": "No billing cycles have fallen due yet.",
        "fr": "Aucune échéance n'est encore arrivée à terme.",
    },
    "pdf.roster.empty": {
        "en": "No students in this class yet.",
        "fr": "Aucun élève dans cette classe.",
    },
    "pdf.monthly.empty": {
        "en": "No active students for this month.",
        "fr": "Aucun élève actif pour ce mois.",
    },
    "pdf.footer": {
        "en": "Generated {generated} · figures as of {as_of}",
        "fr": "Généré le {generated} · chiffres au {as_of}",
    },
    # --- Shared labels for the PDF header blocks ---
    "pdf.field.phone": {"en": "Phone", "fr": "Téléphone"},
    "pdf.field.status": {"en": "Status", "fr": "Statut"},
    "pdf.field.join_date": {"en": "Student since", "fr": "Élève depuis"},
    "pdf.field.first_payment": {"en": "First payment", "fr": "Premier paiement"},
    "pdf.field.repeating": {"en": "Repeating the year", "fr": "Redoublant"},
    "pdf.field.price_note": {"en": "Agreed price", "fr": "Tarif convenu"},
    "pdf.stat.monthly_price": {"en": "Monthly price", "fr": "Tarif mensuel"},
    "pdf.stat.total_paid": {"en": "Total paid", "fr": "Total payé"},
    "pdf.stat.months_overdue": {"en": "Months overdue", "fr": "Mois en retard"},
    "pdf.stat.amount_owed": {"en": "Amount owed", "fr": "Montant dû"},
    "pdf.stat.drift": {"en": "Cumulative drift", "fr": "Retard cumulé"},
    "pdf.stat.students": {"en": "Students", "fr": "Élèves"},
    "pdf.stat.collected": {"en": "Collected", "fr": "Encaissé"},
    "pdf.stat.outstanding": {"en": "Outstanding", "fr": "Solde dû"},
    "pdf.value.yes": {"en": "Yes", "fr": "Oui"},
    "pdf.value.no": {"en": "No", "fr": "Non"},
    "pdf.value.none": {"en": "—", "fr": "—"},
    "pdf.value.days": {"en": "{days} days", "fr": "{days} jours"},
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
