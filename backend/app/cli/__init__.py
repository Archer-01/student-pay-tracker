"""`ardoise`, the admin tool: run on the server (in Northflank's shell) or locally.

It does only what the app can't (decision 0010): accounts, database operations, the API schema,
deleting a student for good, and read-only lookups for support. Everything the teacher does
(students, payments, classes, packs) is done in the app, so there is one door to that data and
one set of checks.
"""

from app.cli import db, money, students, users  # noqa: F401  (each registers its commands)
from app.cli._common import app

__all__ = ["app"]

if __name__ == "__main__":
    app()
