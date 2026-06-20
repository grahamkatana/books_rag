"""
Centralized logging setup, called once at startup by every entrypoint
(the Flask app factory, server.py, and the CLI) so ingestion scripts and
API requests all write to the same place, in the same format, rather
than each entrypoint inventing its own ad-hoc logging.

Two outputs, on purpose:
  - stdout, plain text -- for `docker compose logs`, a local terminal,
    or anything that just wants to tail what's happening right now.
  - a rotating JSON file -- for Promtail to tail and ship to Loki, which
    Grafana then queries. JSON specifically because Loki/Grafana can
    filter and query structured fields (level, logger name, module) far
    more usefully than parsing freeform text lines with regex.

Rotation is size-based (RotatingFileHandler): once app.log exceeds
LOG_MAX_BYTES, it's renamed to app.log.1 (pushing .1->.2, etc.) and a
fresh app.log starts. LOG_BACKUP_COUNT old files are kept beyond the
current one; anything older than that is deleted automatically. This
bounds disk usage regardless of how much log volume the app produces,
which a time-based rotation (daily, etc.) doesn't guarantee on its own.
"""

import logging
import logging.handlers

from pythonjsonlogger.json import JsonFormatter

from app.config import LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return  # calling this more than once (e.g. once from the CLI,
                 # once from a test importing the same process) must not
                 # add duplicate handlers, which would log every line twice
    _configured = True

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    ))
    root.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    ))
    root.addHandler(file_handler)

    # Several libraries this project uses (urllib3, openai, qdrant_client)
    # log at INFO/DEBUG by default and are noisy without adding much --
    # quiet them down to WARNING specifically, without affecting this
    # app's own loggers.
    for noisy in ("urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)