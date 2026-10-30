"""Modelo de vista: lo que el panel y el tooltip muestran, ya decidido.

El JS del panel no decide nada: dibuja este dict tal cual. Asi toda la logica
de presentacion (prioridad, etiquetas, colores, avisos) se prueba aqui.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pr_watch.config import Config
from pr_watch.poller import Health, Snapshot
from pr_watch.polling import Tracked, visible
from pr_watch.providers.base import ChecksState, Provider, PrState, PullRequest, Relation

type Json = dict[str, Any]

APP_TITLE = "PR Watch"

GREEN, AMBER, RED, GRAY = "green", "amber", "red", "gray"


@dataclass(frozen=True, slots=True)
class Status:
    label: str
    tone: str


def status(pr: PullRequest, *, in_review_block: bool) -> Status:
    """Etiqueta y color de una fila, por orden de prioridad."""
    if pr.state is PrState.MERGED:
        return Status("fusionado", GRAY)
    if pr.state is PrState.CLOSED:
        return Status("cerrado", GRAY)
    if pr.conflicts:
        return Status("conflictos", RED)
    if pr.checks is ChecksState.FAILURE:
        return Status("checks fallidos", RED)
    if pr.changes_requested:
        return Status("cambios pedidos", AMBER)
    if pr.ready_to_merge:
        return Status("listo para fusionar", GREEN)
    if pr.approvals:
        return Status(f"aprobado ({len(pr.approvals)})", GREEN)
    if in_review_block and pr.review_pending:
        return Status("te toca", AMBER)
    return Status("sin revisar", AMBER)


def actionable(pr: PullRequest, *, in_review_block: bool) -> bool:
    if pr.state is not PrState.OPEN:
        return False
    if in_review_block:
        return pr.review_pending
    return bool(pr.conflicts) or pr.checks is ChecksState.FAILURE or pr.ready_to_merge


def ordered(items: Iterable[Tracked], *, in_review_block: bool) -> list[Tracked]:
    return sorted(
        items,
        key=lambda t: (
            0 if actionable(t.pr, in_review_block=in_review_block) else 1,
            -t.pr.updated_at.timestamp(),
        ),
    )


def relative(delta: timedelta) -> str:
    secs = max(0, int(delta.total_seconds()))
    if secs < 10:
        return "justo ahora"
    if secs < 60:
        return f"hace {secs} s"
    mins = secs // 60
    if mins < 60:
        return f"hace {mins} min"
    hours = mins // 60
    if hours < 24:
        return f"hace {hours} h"
    days = hours // 24
    return f"hace {days} d"


def clock(t: datetime) -> str:
    return t.astimezone().strftime("%H:%M")


def _checks_text(checks: ChecksState) -> str | None:
    match checks:
        case ChecksState.SUCCESS:
            return "checks ✓"
        case ChecksState.FAILURE:
            return "checks ✗"
        case ChecksState.PENDING:
            return "checks en curso"
        case ChecksState.NONE:
            return None


def subline(pr: PullRequest, *, in_review_block: bool, now: datetime) -> str:
    parts = [pr.repo]
    if in_review_block:
        parts.append(f"de @{pr.author}")
        parts.append(relative(now - pr.updated_at))
    else:
        checks = _checks_text(pr.checks)
        if checks:
            parts.append(checks)
        parts.append(f"{pr.unresolved} sin resolver")
    return " · ".join(parts)


def hover(pr: PullRequest) -> str:
    if pr.approvals:
        return "Aprobado por " + ", ".join(pr.approvals)
    return "Sin aprobaciones"


def _row(
    t: Tracked, provider: Provider, *, in_review_block: bool, unseen: set[str], now: datetime
) -> Json:
    pr = t.pr
    st = status(pr, in_review_block=in_review_block)
    return {
        "id": pr.id,
        "ref": provider.pr_ref(pr),
        "title": pr.title,
        "url": pr.url,
        "label": st.label,
        "tone": st.tone,
        "sub": subline(pr, in_review_block=in_review_block, now=now),
        "hover": hover(pr),
        "unseen": pr.id in unseen,
    }


def _account(snap: Snapshot, provider: Provider | None, cfg: Config) -> list[Json]:
    host = provider.vocabulary.host_label if provider else cfg.provider
    scope = cfg.scope()
    estado = {
        Health.OK: ("Conectado", GREEN),
        Health.STARTING: ("Conectando…", GRAY),
        Health.STALE: ("Sin conexión", AMBER),
        Health.RATE_LIMITED: ("Límite agotado", AMBER),
        Health.INVALID_CREDENTIAL: ("Token rechazado", RED),
        Health.SCOPE_INACCESSIBLE: ("Sin acceso", RED),
        Health.UNCONFIGURED: ("Sin configurar", GRAY),
        Health.UNSUPPORTED: ("No soportado", RED),
    }[snap.health]
    return [
        {"label": "Usuario", "value": snap.login or "—", "tone": ""},
        {
            "label": "Proveedor",
            "value": f"{host} · {provider.scope_label(scope) if provider else scope}"
            if scope
            else host,
            "tone": "",
        },
        {"label": "Estado", "value": estado[0], "tone": estado[1]},
    ]


def _notice(snap: Snapshot, provider: Provider | None, cfg: Config) -> Json | None:
    settings_action = {"label": "Abrir ajustes", "action": "settings"}
    forja = provider.descriptor.display_name if provider else cfg.provider
    match snap.health:
        case Health.UNCONFIGURED:
            return {
                "tone": GRAY,
                "text": "Falta configurar la organización y el token.",
                "action": settings_action,
            }
        case Health.INVALID_CREDENTIAL:
            return {
                "tone": RED,
                "text": f"{forja} rechazó el token: hay que renovarlo.",
                "action": settings_action,
            }
        case Health.SCOPE_INACCESSIBLE:
            return {
                "tone": RED,
                "text": f"Sin acceso: {snap.error}." if snap.error else "Sin acceso al ámbito.",
                "action": settings_action,
            }
        case Health.UNSUPPORTED:
            return {
                "tone": RED,
                "text": f"El proveedor «{cfg.provider}» no está soportado. Revisa config.toml.",
                "action": None,
            }
        case Health.STALE:
            when = f" desde las {clock(snap.last_success)}" if snap.last_success else ""
            return {
                "tone": AMBER,
                "text": f"Datos desactualizados{when}: no se pudo conectar con {forja}.",
                "action": None,
            }
        case Health.RATE_LIMITED:
            until = f" hasta las {clock(snap.suspended_until)}" if snap.suspended_until else ""
            return {
                "tone": AMBER,
                "text": f"Límite de peticiones de {forja} agotado{until}.",
                "action": None,
            }
        case Health.OK | Health.STARTING:
            return None


def panel(
    snap: Snapshot,
    *,
    provider: Provider | None,
    cfg: Config,
    unseen: set[str],
    pinned: bool,
    now: datetime,
    version: str,
) -> Json:
    shows_lists = provider is not None and snap.health not in (
        Health.UNCONFIGURED,
        Health.UNSUPPORTED,
    )
    blocks: list[Json] = []
    empty: str | None = None
    if shows_lists:
        assert provider is not None
        tracked = visible(snap.state)
        mine = [t for t in tracked if t.pr.relation is Relation.AUTHOR]
        review = [t for t in tracked if t.pr.relation is not Relation.AUTHOR]
        for block_id, title, items, relations in (
            ("mine", "MÍOS", mine, (Relation.AUTHOR,)),
            ("review", "POR REVISAR", review, (Relation.REVIEWER, Relation.ASSIGNEE)),
        ):
            in_review = block_id == "review"
            rows = ordered(items, in_review_block=in_review)[: cfg.max_per_block]
            blocks.append(
                {
                    "id": block_id,
                    "title": title,
                    "total": len(items),
                    "link": {
                        "label": "Ver todos",
                        "url": provider.block_url(cfg.scope(), relations),
                    },
                    "rows": [
                        _row(t, provider, in_review_block=in_review, unseen=unseen, now=now)
                        for t in rows
                    ],
                }
            )
        if not mine and not review:
            if snap.health is Health.STARTING:
                empty = f"Consultando {provider.descriptor.display_name}…"
            elif snap.last_success is not None:
                empty = "No hay pull requests abiertos que te involucren."
            blocks = [] if empty else blocks

    return {
        "title": APP_TITLE,
        "pinned": pinned,
        "account": _account(snap, provider, cfg),
        "notice": _notice(snap, provider, cfg),
        "blocks": blocks,
        "empty": empty,
        "footer": {
            "updated_at": int(snap.last_success.timestamp() * 1000) if snap.last_success else None,
            "updated_text": updated_text(snap.last_success, now),
            "version": version,
        },
    }


def updated_text(last_success: datetime | None, now: datetime) -> str:
    if last_success is None:
        return "Sin datos todavía"
    rel = relative(now - last_success)
    return "Actualizado justo ahora" if rel == "justo ahora" else f"Actualizado {rel}"


def tooltip(snap: Snapshot, *, unseen_count: int, provider: Provider | None) -> str:
    name = "pr-watch"
    if snap.health in (
        Health.UNCONFIGURED,
        Health.INVALID_CREDENTIAL,
        Health.SCOPE_INACCESSIBLE,
    ):
        return f"{name} — falta configurar: abre el panel"
    if snap.health is Health.UNSUPPORTED:
        return f"{name} — proveedor no soportado"
    parts: list[str] = []
    if unseen_count > 0:
        parts.append(f"{unseen_count} sin ver")
    if snap.health is Health.STALE:
        since = f" desde las {clock(snap.last_success)}" if snap.last_success else ""
        parts.append(f"datos desactualizados{since}")
    elif snap.health is Health.RATE_LIMITED:
        until = f" hasta las {clock(snap.suspended_until)}" if snap.suspended_until else ""
        parts.append(f"límite agotado{until}")
    elif snap.health is Health.STARTING:
        parts.append("conectando…")
    elif not parts:
        count = len([t for t in visible(snap.state) if t.pr.state is PrState.OPEN])
        noun = provider.vocabulary.noun if provider else "PR"
        when = f" · actualizado a las {clock(snap.last_success)}" if snap.last_success else ""
        parts.append(f"{count} {noun} vigilados{when}")
    return f"{name} — " + " · ".join(parts)
