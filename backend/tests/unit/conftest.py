"""tests/unit holds pure functions only: no database, no app client.

That is what keeps `just test-unit` a sub-second loop and these tests about logic alone. A test
that needs a database belongs in tests/integration; this fails it at setup rather than letting it
quietly slow the unit run down.
"""

import pytest

_NOT_IN_UNIT_TESTS = {"db_engine", "db_session", "client", "anonymous_client", "test_user"}


@pytest.fixture(autouse=True)
def _no_database_in_unit_tests(request: pytest.FixtureRequest) -> None:
    used = _NOT_IN_UNIT_TESTS.intersection(request.fixturenames)
    if used:
        pytest.fail(f"unit tests don't touch the database; move this to tests/integration ({used})")
