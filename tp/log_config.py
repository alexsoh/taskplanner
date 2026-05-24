"""TaskPlanner logging: file (logs/taskplanner.log) + stderr."""

from __future__ import annotations

import logging
import sys

from . import APP_DIR

LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "taskplanner.log"

_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    tp_logger = logging.getLogger("taskplanner")
    tp_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    tp_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)
    tp_logger.addHandler(stream_handler)

    tp_logger.propagate = False
    _configured = True
