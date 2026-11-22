"""Tiny dependency-free i18n for the backend (English + French).

Right-sized for a single-teacher tool: a flat message catalog and two helpers, no gettext/babel.
The **service layer never translates** — it raises structured error *codes*; only the presentation
edges (API error handler, PDFs, CLI) call :func:`translate`. English is the dev default,
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
    "error.payment_amount_precision": {
        "en": "Enter at most two decimal places",
        "fr": "Saisissez au plus deux chiffres après la virgule",
    },
    "error.payment_student_free": {
        "en": "This student pays nothing: change their price before recording a payment",
        "fr": "Cet élève ne paie rien\u00a0: modifiez son tarif avant d'encaisser un paiement",
    },
    "error.payment_raised_for_free_student": {
        "en": "This student pays nothing now: the amount can't go above {recorded} DH",
        "fr": "Cet élève ne paie plus rien\u00a0: le montant ne peut pas dépasser "
        "{recorded}\u00a0DH",
    },
    "error.payment_date_in_future": {
        "en": "The paid date ({paid_date}) can't be in the future",
        "fr": "La date de paiement ({paid_date}) ne peut pas être dans le futur",
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
    "error.pack_price_negative": {
        "en": "Pack price must not be negative",
        "fr": "Le tarif du pack ne peut pas être négatif",
    },
    "error.pack_level_locked": {
        "en": "{student_count} student(s) are on this pack, so its level can no longer change",
        "fr": "{student_count} élève(s) ont ce pack\u00a0: son niveau ne peut plus changer",
    },
    "error.pack_inactive": {
        "en": "Pack {pack_id} is retired and cannot be assigned to a student",
        "fr": "Ce pack n'est plus proposé et ne peut pas être attribué à un élève",
    },
    "error.price_precision": {
        "en": "Enter a price with at most two decimal places",
        "fr": "Saisissez un tarif avec au plus deux chiffres après la virgule",
    },
    "error.custom_price_negative": {
        "en": "Agreed price must not be negative",
        "fr": "Le tarif convenu ne peut pas être négatif",
    },
    # --- Sign-in / accounts (docs/decisions/0005) ---
    # One message for wrong-username, wrong-password and deactivated alike: naming which one
    # failed would let an attacker enumerate accounts.
    "error.invalid_credentials": {
        "en": "Incorrect username or password",
        "fr": "Nom d'utilisateur ou mot de passe incorrect",
    },
    "error.too_many_attempts": {
        "en": "Too many failed sign-in attempts. Try again in {retry_after} seconds.",
        "fr": (
            "Trop de tentatives de connexion échouées. Réessayez dans {retry_after}\u00a0secondes."
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
            "La date de départ ({leave_date}) ne peut pas précéder la date d'arrivée ({entry_date})"
        ),
    },
    "error.return_before_leave": {
        "en": "A return ({entry_date}) cannot precede the last departure ({leave_date})",
        "fr": (
            "La date de retour ({entry_date}) ne peut pas précéder le dernier départ ({leave_date})"
        ),
    },
    # --- Debts ("ne plus réclamer", not the accountant's "abandon de créance") ---
    "error.writeoff_reason_empty": {
        "en": "A write-off needs a reason",
        "fr": "Indiquez pourquoi vous ne réclamez plus cette somme",
    },
    "error.nothing_to_write_off": {
        "en": "Student {student_id} has no outstanding balance to write off",
        "fr": "Cet élève n'a plus rien à régler",
    },
    "warning.returning_with_debt_one": {
        "en": "This student left owing {amount} for {count} month",
        "fr": "Cet élève est parti sans régler {amount} ({count}\u00a0mois)",
    },
    "warning.returning_with_debt_other": {
        "en": "This student left owing {amount} for {count} months",
        "fr": "Cet élève est parti sans régler {amount} ({count}\u00a0mois)",
    },
    # --- Handing the school its share ---
    "error.share_month_not_over": {
        "en": "This month isn't over yet: you can hand over its share after it ends.",
        "fr": "Ce mois n'est pas encore fini\u00a0: vous pourrez remettre sa part après.",
    },
    "error.handover_in_future": {
        "en": "The date can't be in the future.",
        "fr": "La date ne peut pas être dans le futur.",
    },
    "error.nothing_to_hand_over": {
        "en": "Nothing came in that month, so there is no share to hand over.",
        "fr": "Rien n'a été encaissé ce mois-là\u00a0: il n'y a pas de part à remettre.",
    },
    "error.school_share_off": {
        "en": "The school's share is turned off.",
        "fr": "La part de l'école est désactivée.",
    },
    "error.share_outstanding_changed": {
        "en": "The amount to hand over has changed: it is now {amount} DH. "
        "Check it, then try again.",
        "fr": "Le montant à remettre a changé\u00a0: il est maintenant de {amount}\u00a0DH. "
        "Vérifiez-le, puis recommencez.",
    },
    "error.handover_not_found": {
        "en": "That month's share was not marked as handed over.",
        "fr": "La part de ce mois n'a pas été marquée comme remise.",
    },
    # --- Month names: titles ("Octobre 2026") and table rows ---
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
    # --- PDFs: every page ---
    "pdf.teacher": {"en": "Prof. {name}", "fr": "Prof. {name}"},
    "pdf.made_on": {"en": "Made on {date} with Ardoise", "fr": "Établi le {date} avec Ardoise"},
    "pdf.figures_as_of": {"en": "figures as of {date}", "fr": "chiffres au {date}"},
    "pdf.page": {"en": "Page {page} of {total}", "fr": "Page {page} sur {total}"},
    "pdf.total": {"en": "Total", "fr": "Total"},
    # --- PDFs: shared words (the app's own, so paper and screen agree) ---
    "pdf.paid_up": {"en": "Up to date", "fr": "À jour"},
    "pdf.no_price": {"en": "No price", "fr": "Sans tarif"},
    "pdf.free": {"en": "Free", "fr": "Gratuit"},
    "pdf.former": {"en": "Former student", "fr": "Ancien élève"},
    "pdf.on_time": {"en": "On time", "fr": "À l'heure"},
    "pdf.days_late_one": {"en": "{count} day late", "fr": "{count}\u00a0jour de retard"},
    "pdf.days_late_other": {"en": "{count} days late", "fr": "{count}\u00a0jours de retard"},
    "pdf.days_one": {"en": "{count} day", "fr": "{count}\u00a0jour"},
    "pdf.days_other": {"en": "{count} days", "fr": "{count}\u00a0jours"},
    "pdf.months_unpaid_one": {"en": "{count} month unpaid", "fr": "{count}\u00a0mois impayé"},
    "pdf.months_unpaid_other": {"en": "{count} months unpaid", "fr": "{count}\u00a0mois impayés"},
    "pdf.students_one": {"en": "{count} student", "fr": "{count}\u00a0élève"},
    "pdf.students_other": {"en": "{count} students", "fr": "{count}\u00a0élèves"},
    "pdf.no_pack": {"en": "No pack", "fr": "Aucun pack"},
    "pdf.share.yours": {"en": "Your share", "fr": "Votre part"},
    "pdf.share.school": {"en": "School's share ({percent})", "fr": "Part de l'école ({percent})"},
    "pdf.share.school_short": {"en": "School's share", "fr": "Part de l'école"},
    "pdf.share.yours_of": {"en": "of which {amount} is yours", "fr": "dont {amount} pour vous"},
    "pdf.col.student": {"en": "Student", "fr": "Élève"},
    "pdf.col.price": {"en": "Price", "fr": "Tarif"},
    "pdf.col.still_owed": {"en": "Still owed", "fr": "Reste dû"},
    # --- PDFs: a student's history ---
    "pdf.ledger.title": {"en": "Payment history", "fr": "Historique des paiements"},
    "pdf.ledger.owes_one": {
        "en": "{count} month unpaid · {amount}",
        "fr": "{count}\u00a0mois impayé · {amount}",
    },
    "pdf.ledger.owes_other": {
        "en": "{count} months unpaid · {amount}",
        "fr": "{count}\u00a0mois impayés · {amount}",
    },
    "pdf.ledger.oldest_unpaid": {
        "en": "Oldest unpaid month: {month}.",
        "fr": "Le plus ancien mois impayé\u00a0: {month}.",
    },
    "pdf.ledger.next_payment": {
        "en": "Next payment expected on {date}.",
        "fr": "Prochain paiement attendu le {date}.",
    },
    "pdf.ledger.free_text": {
        "en": "This student pays nothing: no payment is asked of them.",
        "fr": "Cet élève ne paie rien\u00a0: aucun paiement ne lui est demandé.",
    },
    "pdf.ledger.no_price_text": {
        "en": "Nothing is charged to this student until they have a pack or an agreed price.",
        "fr": "Rien n'est facturé à cet élève tant qu'il n'a ni pack ni tarif convenu.",
    },
    "pdf.ledger.left": {"en": "Left", "fr": "Parti"},
    "pdf.ledger.left_text": {
        "en": "No longer a student since {date}.",
        "fr": "Ne fait plus partie des élèves depuis le {date}.",
    },
    "pdf.ledger.monthly_price": {"en": "Monthly price", "fr": "Tarif mensuel"},
    "pdf.ledger.agreed_price": {"en": "Agreed price: {note}", "fr": "Tarif convenu\u00a0: {note}"},
    "pdf.ledger.joined": {"en": "Student since", "fr": "Inscrit le"},
    "pdf.ledger.total_paid": {"en": "Total paid", "fr": "Total payé"},
    "pdf.ledger.lateness": {"en": "Days late in total", "fr": "Retards cumulés"},
    "pdf.ledger.school_year": {"en": "{start}–{end} school year", "fr": "Année {start}–{end}"},
    "pdf.ledger.payments": {"en": "Payments received", "fr": "Paiements reçus"},
    "pdf.ledger.col.month": {"en": "Month paid for", "fr": "Mois réglé"},
    "pdf.ledger.col.paid_on": {"en": "Paid on", "fr": "Payé le"},
    "pdf.ledger.col.amount": {"en": "Amount", "fr": "Montant"},
    "pdf.ledger.col.timing": {"en": "Timing", "fr": "Ponctualité"},
    "pdf.ledger.empty": {
        "en": "No payments received yet.",
        "fr": "Aucun paiement reçu pour l'instant.",
    },
    # The words on the month tiles, as on the student page.
    "pdf.tile.paid": {"en": "paid", "fr": "payé"},
    "pdf.tile.late_one": {"en": "{count} d late", "fr": "{count}\u00a0j"},
    "pdf.tile.late_other": {"en": "{count} d late", "fr": "{count}\u00a0j"},
    "pdf.tile.due": {"en": "to pay", "fr": "à payer"},
    "pdf.tile.away": {"en": "away", "fr": "absent"},
    "pdf.tile.upcoming": {"en": "to come", "fr": "à venir"},
    "pdf.tile.free": {"en": "free", "fr": "gratuit"},
    # --- PDFs: the month ---
    "pdf.monthly.eyebrow": {"en": "Monthly report", "fr": "Bilan du mois"},
    "pdf.monthly.collected": {"en": "Collected in {month}", "fr": "Encaissé en {month}"},
    "pdf.monthly.outstanding": {"en": "Unpaid on {date}", "fr": "Impayés au {date}"},
    "pdf.monthly.students": {"en": "Students", "fr": "Élèves"},
    "pdf.monthly.paid_count_one": {
        "en": "{count} paid this month",
        "fr": "{count}\u00a0a payé ce mois-ci",
    },
    "pdf.monthly.paid_count_other": {
        "en": "{count} paid this month",
        "fr": "{count}\u00a0ont payé ce mois-ci",
    },
    "pdf.monthly.by_student": {"en": "By student", "fr": "Par élève"},
    "pdf.monthly.col.paid_in": {"en": "Paid in {month}", "fr": "Payé en {month}"},
    "pdf.monthly.empty": {
        "en": "No active students for this month.",
        "fr": "Aucun élève inscrit ce mois-ci.",
    },
    # --- PDFs: the year ---
    "pdf.annual.eyebrow": {"en": "Annual report", "fr": "Bilan de l'année"},
    "pdf.annual.total": {"en": "Total collected", "fr": "Total encaissé"},
    "pdf.annual.payments": {"en": "Payments", "fr": "Paiements"},
    "pdf.annual.average": {"en": "Monthly average", "fr": "Moyenne mensuelle"},
    "pdf.annual.average_hint": {
        "en": "Over the months with takings",
        "fr": "Sur les mois avec des encaissements",
    },
    "pdf.annual.best": {"en": "Best month", "fr": "Meilleur mois"},
    "pdf.annual.col.month": {"en": "Month", "fr": "Mois"},
    "pdf.annual.col.collected": {"en": "Collected", "fr": "Encaissé"},
    "pdf.annual.to_come": {"en": "to come", "fr": "à venir"},
    "pdf.annual.empty": {
        "en": "No payments were recorded in this year.",
        "fr": "Aucun paiement enregistré cette année.",
    },
    # --- PDFs: a class ---
    "pdf.roster.title": {"en": "Class roster", "fr": "Liste de la classe"},
    "pdf.roster.up_to_date": {"en": "Up to date", "fr": "À jour"},
    "pdf.roster.outstanding": {"en": "Unpaid", "fr": "Impayés"},
    "pdf.roster.col.situation": {"en": "Situation", "fr": "Situation"},
    "pdf.roster.empty": {
        "en": "No students in this class yet.",
        "fr": "Aucun élève dans cette classe pour le moment.",
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


# Abbreviated months: chart and tile labels ("Juin", "Juil") and medium dates ("14 nov. 2026").
_MONTH_SHORT = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "fr": (
        "Janv",
        "Févr",
        "Mars",
        "Avr",
        "Mai",
        "Juin",
        "Juil",
        "Août",
        "Sept",
        "Oct",
        "Nov",
        "Déc",
    ),
}
_MONTH_IN_DATE_FR = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)


def month_short(month: int, locale: str) -> str:
    """ "Juin" / "Jun": short enough for twelve side by side, long enough to tell apart."""
    return _MONTH_SHORT.get(locale, _MONTH_SHORT[DEFAULT_LOCALE])[month - 1]


def month_name(month: int, locale: str, *, in_sentence: bool = False) -> str:
    """ "Octobre", or "octobre" inside a French sentence ("Encaissé en octobre")."""
    name = translate(f"month.{month}", locale)
    return name.lower() if in_sentence and locale == "fr" else name


def format_day(value: date, locale: str) -> str:
    """A date as the app writes it: "14 nov. 2026" / "14 Nov 2026", held on one line."""
    month = _MONTH_IN_DATE_FR[value.month - 1] if locale == "fr" else month_short(value.month, "en")
    return f"{value.day}\u00a0{month}\u00a0{value.year}"


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
