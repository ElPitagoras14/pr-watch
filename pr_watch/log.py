"""Registro en archivo rotativo, con los secretos conocidos tachados."""

from __future__ import annotations

import logging
import logging.handlers
import threading
from pathlib import Path

LOG_FILE = "pr-watch.log"
_REDACTED = "<oculto>"

_secrets: set[str] = set()
_lock = threading.Lock()


def register_secret(value: str) -> None:
    """Anota un valor que nunca debe salir en el registro."""
    # Valores muy cortos tacharian medio registro sin proteger nada.
    if len(value) >= 8:
        with _lock:
            _secrets.add(value)


def redact(text: str) -> str:
    with _lock:
        secrets = list(_secrets)
    for s in secrets:
        if s in text:
            text = text.replace(s, _REDACTED)
    return text


class RedactingFormatter(logging.Formatter):
    """Formatea y despues tacha: cubre mensaje, argumentos y trazas."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup(config_dir: Path, *, level: int = logging.INFO) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / LOG_FILE
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    return path
