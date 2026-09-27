"""In-memory failed-login throttling.

Deliberately **not** a database table. Under the attack this exists to stop, a DB-backed counter
would mean one write per guess on a single-writer SQLite database — the throttle would become the
denial of service. A dict in the one process that serves this app is the right size for it.

The trade is that a restart clears the counters. For a single-instance app that is acceptable: an
attacker cannot force a restart, and they gain one window's worth of guesses if one happens to
occur. Nothing is persisted, so nothing has to be migrated or pruned on disk.

Keyed on **(username, client IP) together**, and that pairing is load-bearing:

- Keyed on username alone, anyone could lock a teacher out of their own account by guessing at it
  from anywhere — turning the protection into the attack.
- Keyed on IP alone, a single NAT'd school or café would share one budget, and a distributed
  attacker would sidestep it entirely.

Requiring both means an attacker must hold an IP steady to burn a username's budget, and burning
it never locks out the real user coming from somewhere else.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

# Ten wrong guesses is far more than a person mistyping a password they know, and far fewer than
# a guessing run needs to be worth starting.
MAX_FAILURES: Final = 10
# Failures older than this stop counting, so an honest mistake today doesn't stack with one a
# week ago.
WINDOW: Final = timedelta(minutes=15)
# How long the pair is refused once it trips.
LOCKOUT: Final = timedelta(minutes=15)
# Ceiling on tracked pairs, so a spray across thousands of invented usernames can't grow the dict
# without bound. Far above anything two real users generate.
MAX_TRACKED: Final = 10_000


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Entry:
    failures: list[datetime] = field(default_factory=list)
    locked_until: datetime | None = None


class LoginThrottle:
    """Tracks failed sign-ins per (username, IP) and locks the pair once they pile up.

    Thread-safe: FastAPI runs the sync login path in a threadpool, so several requests really can
    land here at once.
    """

    def __init__(self, now: Callable[[], datetime] = _utcnow) -> None:
        self._now = now
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._lock = threading.Lock()

    def retry_after(self, username: str, ip: str) -> int | None:
        """Seconds until this pair may try again, or ``None`` if it may try now."""
        key = self._key(username, ip)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.locked_until is None:
                return None
            remaining = (entry.locked_until - self._now()).total_seconds()
            if remaining <= 0:
                # The lock has aged out. Drop the whole entry rather than just clearing the flag,
                # so the next window starts from zero instead of from a full failure list.
                del self._entries[key]
                return None
            return int(remaining) + 1

    def record_failure(self, username: str, ip: str) -> None:
        key = self._key(username, ip)
        now = self._now()
        with self._lock:
            self._prune(now)
            entry = self._entries.setdefault(key, _Entry())
            entry.failures = [at for at in entry.failures if now - at < WINDOW]
            entry.failures.append(now)
            if len(entry.failures) >= MAX_FAILURES:
                entry.locked_until = now + LOCKOUT

    def record_success(self, username: str, ip: str) -> None:
        """Clear the pair's history. A correct password is proof it wasn't a guessing run."""
        with self._lock:
            self._entries.pop(self._key(username, ip), None)

    def reset(self) -> None:
        """Drop all state. For tests — the app never calls this."""
        with self._lock:
            self._entries.clear()

    @staticmethod
    def _key(username: str, ip: str) -> tuple[str, str]:
        return (username.strip().lower(), ip)

    def _prune(self, now: datetime) -> None:
        """Forget entries that have gone quiet. Called on the write path, where the dict grows."""
        if len(self._entries) < MAX_TRACKED:
            return
        stale = [
            key
            for key, entry in self._entries.items()
            if (entry.locked_until is None or entry.locked_until <= now)
            and all(now - at >= WINDOW for at in entry.failures)
        ]
        for key in stale:
            del self._entries[key]


# One instance per process, which is one instance per deployment (single worker by design).
login_throttle = LoginThrottle()
