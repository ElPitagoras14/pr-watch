"""Datos y reglas de la ventana de ajustes, sin interfaz.

El token entra desde la ventana para verificarse y guardarse, pero nunca sale
hacia ella: `load` solo dice si hay uno guardado.

Nada de aqui nombra una forja concreta: los permisos que pedir, el enlace para
crear el token y como se llama el ambito los aporta el proveedor activo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pr_watch import providers
from pr_watch.config import (
    DEFAULT_GITLAB_HOST,
    MAX_PER_BLOCK,
    MIN_INTERVAL_SECS,
    MIN_PER_BLOCK,
    Config,
    clone,
    normalize_host,
)
from pr_watch.providers.base import Descriptor, Provider

type Json = dict[str, Any]

# Con que dibujar la ventana cuando la configuracion no deja construir el
# proveedor (por ejemplo, un host inservible): el usuario tiene que poder
# entrar a arreglarlo.
_SIN_PROVEEDOR = Descriptor(
    display_name="—",
    scope_label="Ámbito",
    scope_placeholder="",
    token_permissions=(),
    create_token_url="",
    configurable_host=True,
)


@dataclass(frozen=True, slots=True)
class Forge:
    """La forja que la ventana tiene seleccionada, aun sin guardar."""

    provider: str
    host: str


def forge_from(payload: Json | None) -> Forge:
    data = payload or {}
    return Forge(
        provider=str(data.get("provider") or "").strip(),
        host=str(data.get("host") or "").strip(),
    )


def apply_forge(base: Config, forge: Forge) -> Config:
    """La configuracion que resultaria de esa seleccion, sin tocar la vigente."""
    cfg = clone(base)
    if forge.provider in providers.REGISTRY:
        cfg.provider = forge.provider
    if cfg.provider == "gitlab":
        cfg.gitlab.host = normalize_host(forge.host) if forge.host else DEFAULT_GITLAB_HOST
    return cfg


def host_of(cfg: Config) -> str:
    """El host de la forja activa; vacio si esa forja no lo configura."""
    return cfg.gitlab.host if cfg.provider == "gitlab" else ""


def forge_changes(before: Config, after: Config) -> bool:
    """Hay que rehacer proveedor, credencial y estado."""
    return before.provider != after.provider or host_of(before) != host_of(after)


def _provider_cards(cfg: Config) -> list[Json]:
    """Como se describe cada forja, no solo la activa.

    El desplegable cambia las etiquetas sin ir al servidor: al elegir GitLab
    la ventana ya sabe que pedir `read_api` y llamar "grupo" al ambito.
    """
    cards: list[Json] = []
    for name, entry in providers.REGISTRY.items():
        probe = providers.create(apply_forge(cfg, Forge(provider=name, host=cfg.gitlab.host)))
        desc = probe.descriptor if probe is not None else _SIN_PROVEEDOR
        cards.append(
            {
                "value": name,
                "label": entry.display_name,
                "needs_host": entry.needs_host,
                "scope_label": desc.scope_label,
                "scope_placeholder": desc.scope_placeholder,
                "permissions": list(desc.token_permissions),
                "noun": probe.vocabulary.noun if probe is not None else "PR",
            }
        )
    return cards


def load(
    cfg: Config,
    provider: Provider | None,
    *,
    has_token: bool,
    plaintext: bool,
    first_run: bool,
) -> Json:
    desc = provider.descriptor if provider is not None else _SIN_PROVEEDOR
    scope = cfg.scope()
    return {
        "provider": cfg.provider,
        "providers": _provider_cards(cfg),
        "forge_label": desc.display_name,
        "host": cfg.gitlab.host,
        "configurable_host": desc.configurable_host,
        "scope_label": desc.scope_label,
        "scope_placeholder": desc.scope_placeholder,
        "scope": scope,
        "scope_display": provider.scope_label(scope) if provider else scope,
        "noun": provider.vocabulary.noun if provider else "PR",
        "has_token": has_token,
        "plaintext_warning": (
            "El token está guardado en texto plano: este sistema no tiene almacén de credenciales."
            if plaintext
            else None
        ),
        "permissions": list(desc.token_permissions),
        "has_create_token_url": bool(desc.create_token_url),
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
    # Con esto no se puede guardar nada: la seleccion no es utilizable.
    error: str = ""

    @property
    def forge(self) -> Forge:
        return Forge(provider=self.config.provider, host=host_of(self.config))


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse(base: Config, payload: Json) -> Parsed:
    """Valida lo que manda la ventana y lo aplica sobre la configuracion vigente."""
    notes: list[str] = []
    error = ""

    forge = forge_from(payload)
    if forge.provider and forge.provider not in providers.REGISTRY:
        notes.append(
            f"El proveedor «{forge.provider}» no está implementado; se conserva el actual."
        )
        forge = Forge(provider=base.provider, host=forge.host)
    cfg = apply_forge(base, forge)
    if cfg.provider == "gitlab" and not cfg.gitlab.host:
        error = "La dirección de la instancia de GitLab no es válida."

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
    return Parsed(config=cfg, scope=scope, token=token, notes=notes, error=error)


def credential_changes(base: Config, parsed: Parsed) -> bool:
    """Hay que verificar antes de guardar si cambia la forja, el token o el ambito."""
    return bool(parsed.token) or parsed.scope != base.scope() or forge_changes(base, parsed.config)
