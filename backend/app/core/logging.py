"""Logging setup shared by the API and, later, background generation jobs."""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers when the app factory runs more than once (tests, reload).
    if not any(getattr(h, "_ai_architect", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._ai_architect = True  # type: ignore[attr-defined]
        root.addHandler(handler)
