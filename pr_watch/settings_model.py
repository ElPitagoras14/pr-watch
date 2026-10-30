"""Datos y reglas de la ventana de ajustes, sin interfaz.

El token entra desde la ventana para verificarse y guardarse, pero nunca sale
hacia ella: `load` solo dice si hay uno guardado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pr_watch.config import (
    MAX_PER_BLOCK,
    MIN_INTERVAL_SECS,
    MIN_PER_BLOCK,
    Config,
    clone,
)
from pr_watch.providers import github

type Json = dict[str, Any]


def load(cfg: Config, *, has_token: bool, plaintext: bool, first_run: bool) -> Json:
    return {
        "provider": "github.com",
        "scope_label": "Cuenta u organización",
        "scope": cfg.scope(),
        "scope_display": github.GitHubProvider().scope_label(cfg.scope()),
        "has_token": has_token,
        "plaintext_warning": (
            "El token está guardado en texto plano: este sistema no tiene almacén de credenciales."
            if plaintext
            else None
        ),
        "permissions": list(github.TOKEN_PERMISSIONS),
        "create_token_url": github.CREATE_TOKEN_URL,
        "poll_interval_secs": cfg.poll_interval_secs,
        "min_interval_secs": MIN_INTERVAL_SECS,
        "max_per_block": cfg.max_per_block,
        "min_per_block": MIN_PER_BLOCK,
        "max_per_block_limit": MAX_PER_BLOCK,
        "notifications": cfg.notifications,
        "first_run": first_run,
    }


@dataclass(slots=True)
class Parsed:
    config: Config
    scope: str
    token: str  # vacio = conservar el guardado
    notes: list[str]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse(base: Config, payload: Json) -> Parsed:
    """Valida lo que manda la ventana y lo aplica sobre la configuracion vigente."""
    notes: list[str] = []
    cfg = clone(base)

    interval = _as_int(payload.get("poll_interval_secs"), cfg.poll_interval_secs)
    if interval < MIN_INTERVAL_SECS:
        notes.append(f"El intervalo mínimo es {MIN_INTERVAL_SECS} s; se usa {MIN_INTERVAL_SECS}.")
        interval = MIN_INTERVAL_SECS
    cfg.poll_interval_secs = interval

    per_block = _as_int(payload.get("max_per_block"), cfg.max_per_block)
    clamped = min(max(per_block, MIN_PER_BLOCK), MAX_PER_BLOCK)
    if clamped != per_block:
        notes.append(f"El tope va de {MIN_PER_BLOCK} a {MAX_PER_BLOCK}; se usa {clamped}.")
    cfg.max_per_block = clamped

    cfg.notifications = bool(payload.get("notifications", cfg.notifications))

    scope = str(payload.get("scope") or "").strip()
    token = str(payload.get("token") or "").strip()
    return Parsed(config=cfg, scope=scope, token=token, notes=notes)


def credential_changes(base: Config, parsed: Parsed) -> bool:
    """Hay que verificar antes de guardar si cambia el token o el ambito."""
    return bool(parsed.token) or parsed.scope != base.scope()
