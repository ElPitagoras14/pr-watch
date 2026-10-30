"""Diferencia entre sondeos: novedades, caducidad de terminales y purga.

Todo es puro: recibe el estado anterior y el resultado nuevo y devuelve el
estado siguiente con las novedades detectadas. Ni red ni reloj propios.
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pr_watch.providers.base import (
    ChecksState,
    FetchResult,
    Inaccessible,
    PrState,
    PullRequest,
)


@dataclass(frozen=True, slots=True)
class Tracked:
    pr: PullRequest
    # Cuando se detecto que paso a fusionado o cerrado; None si sigue abierto.
    terminal_since: datetime | None = None
    # Hechos notificables ya avisados y aun vigentes (ver notify.py).
    notified: frozenset[str] = frozenset()


@dataclass(slots=True)
class State:
    prs: dict[str, Tracked] = field(default_factory=dict[str, Tracked])
    # False hasta completar el primer sondeo: ese sondeo fija la linea base.
    baseline: bool = False


class Kind(enum.StrEnum):
    NEW = "new"
    APPROVALS = "approvals"
    CHANGES_REQUESTED = "changes_requested"
    CHECKS_FAILED = "checks_failed"
    CHECKS_PASSED = "checks_passed"
    CONFLICTS = "conflicts"
    MERGED = "merged"
    CLOSED = "closed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class Novelty:
    pr_id: str
    kind: Kind


@dataclass(slots=True)
class Outcome:
    state: State
    novelties: list[Novelty]


def missing_ids(state: State, result: FetchResult) -> list[str]:
    """Abiertos conocidos que no vinieron en el listado: hay que preguntar por ellos."""
    fetched = {pr.id for pr in result.prs}
    return [
        pid
        for pid, t in state.prs.items()
        if t.terminal_since is None and not t.pr.draft and pid not in fetched
    ]


def _changes(old: PullRequest, new: PullRequest) -> list[Kind]:
    kinds: list[Kind] = []
    if len(old.approvals) != len(new.approvals):
        kinds.append(Kind.APPROVALS)
    if new.changes_requested and not old.changes_requested:
        kinds.append(Kind.CHANGES_REQUESTED)
    if new.checks != old.checks:
        if new.checks is ChecksState.FAILURE:
            kinds.append(Kind.CHECKS_FAILED)
        elif new.checks is ChecksState.SUCCESS:
            kinds.append(Kind.CHECKS_PASSED)
    if new.conflicts is True and old.conflicts is not True:
        kinds.append(Kind.CONFLICTS)
    if new.unresolved != old.unresolved:
        kinds.append(Kind.UNRESOLVED)
    return kinds


def apply(
    prev: State,
    result: FetchResult,
    missing_states: dict[str, PrState | Inaccessible] | None,
    *,
    now: datetime,
    ttl: timedelta,
) -> Outcome:
    """Calcula el estado siguiente y las novedades de un sondeo correcto.

    `missing_states` es el estado actual de los que dejaron de aparecer
    (`missing_ids`), o None si no se pudo consultar.
    """
    record = prev.baseline
    novelties: list[Novelty] = []
    out: dict[str, Tracked] = {}
    fetched_ids: set[str] = set()

    for pr in result.prs:
        fetched_ids.add(pr.id)
        old = prev.prs.get(pr.id)
        if pr.conflicts is None and old is not None and old.pr.conflicts is not None:
            pr = dataclasses.replace(pr, conflicts=old.pr.conflicts)
        notified = old.notified if old is not None else frozenset[str]()
        out[pr.id] = Tracked(pr=pr, notified=notified)
        if not record or pr.draft:
            continue
        is_new = old is None or old.pr.draft or old.terminal_since is not None
        if is_new:
            novelties.append(Novelty(pr.id, Kind.NEW))
        else:
            assert old is not None
            novelties.extend(Novelty(pr.id, k) for k in _changes(old.pr, pr))

    for pid, old in prev.prs.items():
        if pid in fetched_ids:
            continue
        if old.terminal_since is not None:
            if now - old.terminal_since < ttl:
                out[pid] = old
            continue
        if old.pr.draft:
            # Un borrador que desaparece no avisa de nada: nunca se mostro.
            if not result.complete:
                out[pid] = old
            continue
        if not result.complete:
            out[pid] = old
            continue
        current = missing_states.get(pid) if missing_states is not None else None
        match current:
            case PrState.MERGED | PrState.CLOSED:
                terminal = dataclasses.replace(old.pr, state=current)
                if ttl > timedelta(0):
                    out[pid] = Tracked(pr=terminal, terminal_since=now, notified=old.notified)
                if record:
                    kind = Kind.MERGED if current is PrState.MERGED else Kind.CLOSED
                    novelties.append(Novelty(pid, kind))
            case PrState.OPEN:
                # Sigue abierto pero ya no te involucra: sale sin novedad.
                pass
            case Inaccessible():
                # Purga silenciosa: perder acceso no es un hecho sobre el PR.
                pass
            case None:
                # No se pudo consultar su estado: se conserva hasta saberlo.
                out[pid] = old

    return Outcome(State(prs=out, baseline=True), novelties)


def expire(state: State, *, now: datetime, ttl: timedelta) -> State:
    """Quita los terminales caducados (al arrancar y entre sondeos)."""
    kept = {
        pid: t
        for pid, t in state.prs.items()
        if t.terminal_since is None or now - t.terminal_since < ttl
    }
    return State(prs=kept, baseline=state.baseline)


def visible(state: State) -> list[Tracked]:
    """Lo que se muestra: todo menos los borradores."""
    return [t for t in state.prs.values() if not t.pr.draft]
