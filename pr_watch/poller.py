"""Bucle de sondeo: cuando consultar, que hacer con el resultado y con los fallos.

Corre en su propio hilo. La interfaz nunca espera por el: recibe instantaneas
por `on_update` y pide sondeos con `request_refresh`.
"""

from __future__ import annotations

import enum
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pr_watch import notify, polling, state_store
from pr_watch.credential import Token
from pr_watch.polling import Novelty, State
from pr_watch.providers.base import (
    InvalidCredential,
    Provider,
    ProviderError,
    RateLimited,
    ScopeInaccessible,
)

_log = logging.getLogger(__name__)


class Health(enum.Enum):
    UNCONFIGURED = "unconfigured"  # falta token u organizacion
    UNSUPPORTED = "unsupported"  # proveedor desconocido
    STARTING = "starting"  # configurado, aun sin primer resultado
    OK = "ok"
    STALE = "stale"  # el ultimo sondeo fallo; se muestran datos viejos
    INVALID_CREDENTIAL = "invalid_credential"
    SCOPE_INACCESSIBLE = "scope_inaccessible"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True, slots=True)
class Snapshot:
    health: Health
    state: State
    login: str | None = None
    last_success: datetime | None = None
    suspended_until: datetime | None = None
    error: str = ""
    novelties: list[Novelty] = field(default_factory=list[Novelty])
    notices: list[notify.Notice] = field(default_factory=list[notify.Notice])


@dataclass(slots=True)
class Settings:
    scope: str
    token: Token | None
    interval: timedelta
    ttl: timedelta


class Poller:
    def __init__(
        self,
        provider: Provider | None,
        settings: Settings,
        state: State,
        state_path: Path | None,
        on_update: Callable[[Snapshot], None],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.provider = provider
        self.settings = settings
        self.state = polling.expire(state, now=now(), ttl=settings.ttl)
        self.state_path = state_path
        self.on_update = on_update
        self.now = now

        self.login: str | None = None
        self.last_success: datetime | None = None
        self.suspended_until: datetime | None = None
        self.health = self._idle_health()
        self.error = ""

        self._poll_lock = threading.Lock()
        self._settings_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Sube con cada cambio de forja: un sondeo que estaba en vuelo cuando
        # se cambio no debe escribir su resultado sobre el estado del nuevo.
        self._generation = 0

    # ---- estado para la interfaz ----

    def snapshot(
        self,
        novelties: list[Novelty] | None = None,
        notices: list[notify.Notice] | None = None,
    ) -> Snapshot:
        return Snapshot(
            health=self.health,
            state=self.state,
            login=self.login,
            last_success=self.last_success,
            suspended_until=self.suspended_until,
            error=self.error,
            novelties=novelties or [],
            notices=notices or [],
        )

    def _idle_health(self) -> Health:
        if self.provider is None:
            return Health.UNSUPPORTED
        if self.settings.token is None or not self.settings.scope:
            return Health.UNCONFIGURED
        return Health.STARTING

    def can_poll(self) -> bool:
        return self.health not in (
            Health.UNSUPPORTED,
            Health.UNCONFIGURED,
            Health.INVALID_CREDENTIAL,
            Health.SCOPE_INACCESSIBLE,
        )

    def is_suspended(self) -> bool:
        return self.suspended_until is not None and self.now() < self.suspended_until

    # ---- control ----

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def request_refresh(self) -> bool:
        """Pide un sondeo ya. False si no se lanzara (suspendido o sin configurar)."""
        if self.is_suspended() or not self.can_poll():
            return False
        self._wake.set()
        return True

    def reconfigure(self, settings: Settings) -> None:
        """Aplica ajustes nuevos sin reiniciar. Un cambio de credencial reinicia el estado."""
        with self._settings_lock:
            credential_changed = (
                settings.token != self.settings.token or settings.scope != self.settings.scope
            )
            self.settings = settings
            if credential_changed:
                self.login = None
                self.error = ""
                self.suspended_until = None
                self.health = self._idle_health()
        self.on_update(self.snapshot())
        self._wake.set()

    def rebind(
        self,
        provider: Provider | None,
        settings: Settings,
        state: State,
        state_path: Path | None,
    ) -> None:
        """Cambia de forja sin reiniciar el hilo de sondeo.

        Quien llama es responsable de haber persistido antes el estado de la
        forja que se abandona: aqui ya se sustituye.
        """
        with self._settings_lock:
            self._generation += 1
            self.provider = provider
            self.settings = settings
            self.state = polling.expire(state, now=self.now(), ttl=settings.ttl)
            self.state_path = state_path
            self.login = None
            self.last_success = None
            self.suspended_until = None
            self.error = ""
            self.health = self._idle_health()
        self.on_update(self.snapshot())
        self._wake.set()

    # ---- bucle ----

    def next_delay(self) -> float | None:
        """Segundos hasta el proximo sondeo, o None si hay que esperar a que lo pidan."""
        if not self.can_poll():
            return None
        if self.is_suspended():
            assert self.suspended_until is not None
            return max(1.0, (self.suspended_until - self.now()).total_seconds())
        return self.settings.interval.total_seconds()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.can_poll() and not self.is_suspended():
                self.poll_once()
            delay = self.next_delay()
            self._wake.wait(timeout=delay)
            self._wake.clear()

    def poll_once(self) -> bool:
        """Un sondeo completo. False si ya habia uno en curso o no procede."""
        if not self._poll_lock.acquire(blocking=False):
            return False
        try:
            with self._settings_lock:
                settings = self.settings
                generation = self._generation
                provider = self.provider
            if provider is None or settings.token is None or not settings.scope:
                self.health = self._idle_health()
                self.on_update(self.snapshot())
                return False
            if self.is_suspended():
                return False
            novelties, notices = self._poll(provider, settings, settings.token, generation)
            if generation != self._generation:
                return False
            self.on_update(self.snapshot(novelties, notices))
            return True
        finally:
            self._poll_lock.release()

    def _stale(self, generation: int) -> bool:
        """La forja cambio mientras este sondeo estaba en vuelo."""
        if generation == self._generation:
            return False
        _log.info("Sondeo descartado: la forja cambio mientras se consultaba")
        return True

    def _poll(
        self, provider: Provider, settings: Settings, token: Token, generation: int
    ) -> tuple[list[Novelty], list[notify.Notice]]:
        try:
            if self.login is None:
                self.login = provider.verify(settings.scope, token).login
            result = provider.fetch_open(settings.scope, token)
            missing = polling.missing_ids(self.state, result) if result.complete else []
            missing_states = provider.fetch_states(missing, token) if missing else {}
        except RateLimited as e:
            if self._stale(generation):
                return [], []
            self.suspended_until = e.reset_at
            self.health = Health.RATE_LIMITED
            self.error = str(e)
            _log.warning("Limite de peticiones agotado hasta %s", e.reset_at.isoformat())
            return [], []
        except InvalidCredential as e:
            if self._stale(generation):
                return [], []
            self.health = Health.INVALID_CREDENTIAL
            self.error = str(e)
            _log.warning("Credencial rechazada: %s", e)
            return [], []
        except ScopeInaccessible as e:
            if self._stale(generation):
                return [], []
            self.health = Health.SCOPE_INACCESSIBLE
            self.error = str(e)
            _log.warning("Ambito inaccesible: %s", e)
            return [], []
        except ProviderError as e:
            if self._stale(generation):
                return [], []
            self.health = Health.STALE
            self.error = str(e) or type(e).__name__
            _log.warning("Sondeo fallido: %s", self.error)
            return [], []

        if self._stale(generation):
            return [], []
        if result.errors:
            _log.warning("Sondeo incompleto: %s", "; ".join(result.errors))
        now = self.now()
        outcome = polling.apply(self.state, result, missing_states, now=now, ttl=settings.ttl)
        state, notices = notify.evaluate(
            outcome.state, record=self.state.baseline, ref=provider.pr_ref
        )
        self.state = state
        self.last_success = now
        self.suspended_until = None
        self.health = Health.OK
        self.error = ""
        self._persist()
        return outcome.novelties, notices

    def tick(self) -> None:
        """Caducidad de terminales entre sondeos (la llama la interfaz al dibujar)."""
        expired = polling.expire(self.state, now=self.now(), ttl=self.settings.ttl)
        if len(expired.prs) != len(self.state.prs):
            self.state = expired
            self._persist()

    def _persist(self) -> None:
        if self.state_path is None:
            return
        try:
            state_store.save(self.state, self.state_path)
        except OSError as e:
            _log.warning("No se pudo guardar el estado: %s", e)

    def save_now(self) -> None:
        self._persist()
