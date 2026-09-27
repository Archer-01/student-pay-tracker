"""LoginThrottle — the counter that turns argon2's slowness into an actual limit.

Pure unit tests with an injected clock: the behaviour is entirely about elapsed time, and a suite
that used real time would either sleep for 15 minutes or test nothing.
"""

from datetime import UTC, datetime, timedelta

from app.core.throttle import LOCKOUT, MAX_FAILURES, WINDOW, LoginThrottle

IP = "203.0.113.7"
OTHER_IP = "198.51.100.2"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _throttle() -> tuple[LoginThrottle, Clock]:
    clock = Clock()
    return LoginThrottle(now=clock), clock


def _fail(throttle: LoginThrottle, times: int, username: str = "aymen", ip: str = IP) -> None:
    for _ in range(times):
        throttle.record_failure(username, ip)


def test_a_fresh_pair_is_allowed() -> None:
    throttle, _ = _throttle()
    assert throttle.retry_after("aymen", IP) is None


def test_a_few_failures_do_not_lock() -> None:
    """Mistyping a password you know must not lock you out."""
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES - 1)
    assert throttle.retry_after("aymen", IP) is None


def test_it_locks_at_the_limit() -> None:
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES)
    retry = throttle.retry_after("aymen", IP)
    assert retry is not None and retry > 0


def test_the_lock_expires_on_its_own() -> None:
    throttle, clock = _throttle()
    _fail(throttle, MAX_FAILURES)
    clock.advance(LOCKOUT + timedelta(seconds=1))
    assert throttle.retry_after("aymen", IP) is None


def test_retry_after_shrinks_as_the_lock_ages() -> None:
    throttle, clock = _throttle()
    _fail(throttle, MAX_FAILURES)
    first = throttle.retry_after("aymen", IP)
    clock.advance(timedelta(minutes=5))
    second = throttle.retry_after("aymen", IP)
    assert first is not None and second is not None
    assert second < first


def test_failures_outside_the_window_do_not_count() -> None:
    """An honest mistake last week must not stack with one today."""
    throttle, clock = _throttle()
    _fail(throttle, MAX_FAILURES - 1)
    clock.advance(WINDOW + timedelta(seconds=1))
    _fail(throttle, 1)
    assert throttle.retry_after("aymen", IP) is None


def test_a_successful_sign_in_clears_the_history() -> None:
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES - 1)
    throttle.record_success("aymen", IP)
    _fail(throttle, MAX_FAILURES - 1)
    assert throttle.retry_after("aymen", IP) is None


def test_locking_one_ip_does_not_lock_the_real_user_elsewhere() -> None:
    """The whole reason the key includes the IP: otherwise guessing at a username from anywhere
    would lock its owner out, and the protection would become the attack."""
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES, ip=IP)

    assert throttle.retry_after("aymen", IP) is not None
    assert throttle.retry_after("aymen", OTHER_IP) is None


def test_locking_one_username_does_not_lock_another_from_the_same_ip() -> None:
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES, username="aymen")
    assert throttle.retry_after("ayoub", IP) is None


def test_the_username_half_of_the_key_is_case_and_space_insensitive() -> None:
    """Must match how AuthService normalizes, or "AYMEN" would get a fresh budget every time."""
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES, username="aymen")
    assert throttle.retry_after("  AYMEN  ", IP) is not None


def test_an_expired_lock_starts_the_next_window_from_zero() -> None:
    """Otherwise the stale failure list would re-trip the lock on the first new mistake."""
    throttle, clock = _throttle()
    _fail(throttle, MAX_FAILURES)
    clock.advance(LOCKOUT + timedelta(seconds=1))
    assert throttle.retry_after("aymen", IP) is None

    _fail(throttle, 1)
    assert throttle.retry_after("aymen", IP) is None


def test_reset_clears_everything() -> None:
    throttle, _ = _throttle()
    _fail(throttle, MAX_FAILURES)
    throttle.reset()
    assert throttle.retry_after("aymen", IP) is None
