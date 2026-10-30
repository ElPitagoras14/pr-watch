"""Notificaciones del sistema: solo lo accionable, una vez por hecho.

`evaluate` es pura: compara los hechos vigentes de cada PR con los ya
avisados (guardados en el estado) y devuelve los avisos nuevos. La emision
real va aparte, en `Notifier`, porque depende del sistema.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from pr_watch.polling import State, Tracked
from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation

_log = logging.getLogger(__name__)

GROUP_ABOVE = 3

READY, BROKEN, CHANGES, REVIEW = "ready", "broken", "changes", "review"


@dataclass(frozen=True, slots=True)
class Notice:
    title: str
    body: str
    url: str | None  # None = notificacion agrupada: abre el panel


def facts(pr: PullRequest) -> set[str]:
    """Hechos notificables vigentes de un PR."""
    if pr.state is not PrState.OPEN or pr.draft:
        return set()
    out: set[str] = set()
    if pr.relation is Relation.AUTHOR:
        if pr.ready_to_merge:
            out.add(READY)
        if pr.conflicts or pr.checks is ChecksState.FAILURE:
            out.add(BROKEN)
        if pr.changes_requested:
            out.add(CHANGES)
    elif pr.relation is Relation.REVIEWER and pr.review_pending:
        out.add(REVIEW)
    return out


def _notice(pr: PullRequest, fact: str, ref: str) -> Notice:
    head = f"{ref} {pr.title}"
    match fact:
        case "ready":
            return Notice("Listo para fusionar", f"{head}\n{pr.repo}", pr.url)
        case "broken":
            why = "Conflictos" if pr.conflicts else "Checks fallidos"
            return Notice(why, f"{head}\n{pr.repo}", pr.url)
        case "changes":
            return Notice("Cambios pedidos", f"{head}\n{pr.repo}", pr.url)
        case _:
            return Notice("Te piden revisión", f"{head}\n{pr.repo} · de @{pr.author}", pr.url)


def evaluate(
    state: State, *, record: bool, ref: Callable[[PullRequest], str]
) -> tuple[State, list[Notice]]:
    """Avisos nuevos y el estado con los hechos avisados actualizados.

    Los hechos se anotan aunque las notificaciones esten apagadas o sea la
    linea base, para que activarlas no dispare una avalancha de lo ya sabido.
    """
    notices: list[Notice] = []
    prs: dict[str, Tracked] = {}
    for pid, t in state.prs.items():
        active = facts(t.pr)
        if record:
            for fact in sorted(active - t.notified):
                notices.append(_notice(t.pr, fact, ref(t.pr)))
        prs[pid] = dataclasses.replace(t, notified=frozenset(active))
    if len(notices) > GROUP_ABOVE:
        refs = ", ".join(n.body.split(" ", 1)[0] for n in notices[:GROUP_ABOVE])
        notices = [Notice(f"pr-watch: {len(notices)} novedades", f"{refs} y más", None)]
    return State(prs=prs, baseline=state.baseline), notices


class Notifier:
    """Emite con desktop-notifier en un bucle asyncio propio.

    Si el sistema no puede emitir, lo registra una sola vez y deja de
    intentarlo hasta que se vuelva a activar la preferencia.
    """

    def __init__(
        self, on_open_url: Callable[[str], None], on_open_panel: Callable[[], None]
    ) -> None:
        self.on_open_url = on_open_url
        self.on_open_panel = on_open_panel
        self._loop: asyncio.AbstractEventLoop | None = None
        self._notifier: object | None = None
        self.broken = False
        self._lock = threading.Lock()

    def reset(self) -> None:
        self.broken = False

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="notifier", daemon=True).start()
                self._loop = loop
            return self._loop

    def emit(self, notices: list[Notice]) -> None:
        if not notices or self.broken:
            return
        loop = self._ensure()
        for n in notices:
            fut = asyncio.run_coroutine_threadsafe(self._send(n), loop)
            fut.add_done_callback(self._done)

    def _done(self, fut: object) -> None:
        exc = fut.exception()  # type: ignore[attr-defined]
        if exc is not None and not self.broken:
            self.broken = True
            _log.warning("No se pueden emitir notificaciones: %s", exc)

    async def _send(self, n: Notice) -> None:
        from desktop_notifier import DesktopNotifier

        if self._notifier is None:
            self._notifier = DesktopNotifier(app_name="pr-watch")
        notifier: DesktopNotifier = self._notifier  # type: ignore[assignment]
        url = n.url

        def clicked() -> None:
            if url is None:
                self.on_open_panel()
            else:
                self.on_open_url(url)

        await notifier.send(title=n.title, message=n.body, on_clicked=clicked)
