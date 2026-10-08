"""Structured logging setup.

JSON in production (parseable by a log aggregator), human-readable locally.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    json_format = (
        '{"time":"%(asctime)s","level":"%(levelname)s",'
        '"logger":"%(name)s","message":"%(message)s"}'
    )
    log_format = (
        "%(asctime)s %(levelname)-8s %(name)s %(message)s"
        if settings.environment == "local"
        else json_format
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    # Keep pytest/caplog and double-initialization safe.
    if not root.handlers:
        root.addHandler(handler)

    # Quiet noisy libraries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.getLogger("devpulse").info(
        "Logging configured", extra={"environment": settings.environment}
    )
