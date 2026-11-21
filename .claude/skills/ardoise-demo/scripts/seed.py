"""Demo data for a scratch Ardoise, through the API as the app would enter it.

Every date is relative to today, so the demo always looks like the middle of a school year: about
a dozen students across three classes, most paying, some late, a few owing, one who left owing,
one on a custom price, one with a note. Run by demo.sh against a fresh database; needs only the
standard library. API base from $API (default http://127.0.0.1:8001/api/v1).
"""

import http.cookiejar
import json
import os
import urllib.request
import zlib
from datetime import date, timedelta

API = os.environ.get("API", "http://127.0.0.1:8001/api/v1")
TODAY = date.today()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, method=method, data=data, headers={"Content-Type": "application/json"}
    )
    with _opener.open(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def add_months(d: date, n: int) -> date:
    """`d` moved by `n` calendar months, the day clamped to the month's length (as the backend)."""
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


# September of the current school year: the demo's students mostly join then.
SCHOOL_YEAR = date(TODAY.year if TODAY.month >= 9 else TODAY.year - 1, 9, 1)


def joined(months_after_september: int, day: int) -> date:
    return add_months(SCHOOL_YEAR, months_after_september).replace(day=day)


call("POST", "/auth/login", {"username": "aymen", "password": "demo-pass-123"})
classes = {
    level: call("POST", "/classes", {"level": level, "name": "Groupe A"})["id"]
    for level in ("TC", "1BAC", "2BAC")
}


def pack(name: str, level: str, price: str, subjects: list[str]) -> int:
    body = {"name": name, "level": level, "price": price, "subjects": subjects}
    return call("POST", "/packs", body)["id"]


packs = {
    "tc": pack("Pack TC Sciences", "TC", "200", ["Maths", "Physique"]),
    "1bac": pack("Pack 1BAC Sciences", "1BAC", "220", ["Maths", "Physique"]),
    "2bac": pack("Pack 2BAC Sciences Maths", "2BAC", "300", ["Maths", "Physique"]),
    "maths": pack("Maths seul", "2BAC", "150", ["Maths"]),
}


def student(
    first: str,
    last: str,
    level: str,
    pack_key: str,
    join: date,
    amount: str,
    late: list[int],
    owing: int = 0,
    paid_months: int | None = None,
    **extra: object,
) -> int:
    """Enrol, then pay every month due so far except the last `owing` (or only the first
    `paid_months`), `late[i % len]` days after each due date (never in the future)."""
    phone = "06" + str(zlib.crc32(f"{first} {last}".encode()) % 10**8).zfill(8)
    body = {"first_name": first, "last_name": last, "phone": phone, "join_date": join.isoformat()}
    body |= {"class_id": classes[level], "pack_id": packs[pack_key], **extra}
    sid = call("POST", "/students", body)["id"]

    dues = []
    k = 0
    while (due := add_months(join, k)) <= TODAY:
        dues.append(due)
        k += 1
    to_pay = dues[: max(0, len(dues) - owing)] if paid_months is None else dues[:paid_months]
    for i, due in enumerate(to_pay):
        paid = min(due + timedelta(days=late[i % len(late)]), TODAY)
        payment = {"for_month": due.strftime("%Y-%m"), "paid_date": paid.isoformat()}
        call("POST", f"/students/{sid}/payments", payment | {"amount": amount})
    return sid


# A full year behind them: the annual report and the school-year tiles have history.
student("Youssef", "El Amrani", "2BAC", "2bac", joined(-12, 5), "300", [0, 3, 0, 12, 0, 6])
student("Salma", "Ouazzani", "2BAC", "2bac", joined(0, 5), "300", [8, 9, 7])  # "Un peu tard"
student("Amina", "Benali", "2BAC", "maths", joined(0, 10), "150", [0], owing=2)
student("Karim", "Bennis", "TC", "tc", joined(0, 8), "200", [0])
student("Nora", "Chraibi", "1BAC", "1bac", joined(0, 12), "220", [0, 1])
student("Omar", "Tazi", "TC", "tc", joined(0, 15), "200", [2], owing=1)
student("Sara", "Idrissi", "1BAC", "1bac", joined(0, 3), "220", [14, 20], owing=1)  # "Souvent tard"
student(
    "Ilyas", "Tahiri", "TC", "tc", joined(0, 20), "150", [0],
    custom_price="150", price_note="Remise fratrie",
)  # fmt: skip
student(
    "Imane", "Zerouali", "1BAC", "1bac", joined(0, 5), "220", [0],
    note="Paie toujours le samedi, en espèces.",
)  # fmt: skip
student("Hamza", "Berrada", "2BAC", "2bac", joined(1, 2), "300", [4])
# Due this week: joined a few days from now, a month ago, so the next due falls within 7 days.
student("Lina", "Fassi", "1BAC", "1bac", add_months(TODAY + timedelta(days=3), -1), "220", [0])
# Left owing: paid September only, gone after October's due date.
mehdi = student("Mehdi", "Alaoui", "TC", "tc", joined(0, 5), "200", [0], paid_months=1)
if TODAY > joined(1, 20):
    call("POST", f"/students/{mehdi}/leave", {"leave_date": joined(1, 20).isoformat()})
print("seeded 12 students")
