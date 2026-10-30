"""Novedades sin ver: el buzon detras del punto del icono y de las marcas.

No es el numero de pendientes: cuenta lo que paso desde la ultima vez que se
abrio el panel. No se persiste: al arrancar vale cero.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from pr_watch.polling import Novelty


class Inbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.count = 0
        self.marks: set[str] = set()
        self.panel_visible = False

    def add(self, novelties: Iterable[Novelty]) -> None:
        with self._lock:
            items = list(novelties)
            self.marks.update(n.pr_id for n in items)
            # Con el panel a la vista el usuario ya lo esta mirando: se marca
            # la fila pero no suma.
            if not self.panel_visible:
                self.count += len(items)

    def panel_opened(self) -> None:
        with self._lock:
            self.panel_visible = True
            self.count = 0

    def panel_closed(self) -> None:
        with self._lock:
            self.panel_visible = False
            self.marks.clear()

    def unseen_ids(self) -> set[str]:
        with self._lock:
            return set(self.marks)
