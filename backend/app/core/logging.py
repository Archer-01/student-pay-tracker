"""Minimal stdlib logging setup — right-sized for a single-teacher app.

No structlog / correlation IDs; just a sensible format so app messages and handled errors leave a
trace. Uvicorn provides request/access logs on top of this.
"""

import logging
import os


def configure_logging(level: str | int | None = None) -> None:
    logging.basicConfig(
        level=level or os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
