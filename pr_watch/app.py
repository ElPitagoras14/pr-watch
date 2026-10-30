"""Cableado de la aplicacion: ventanas, bandeja, sondeo, novedades y ajustes.

Hilos (verificado en el spike de la tarea 1.2):
- Principal: `webview.start()`, que exige el hilo principal. Ahi viven el panel
  (creado oculto al arrancar, para que abrirlo sea instantaneo) y los ajustes.
- Bandeja: en Windows, `pystray.Icon.run()` en un hilo propio con su bucle de
  mensajes; en Linux, `run_detached()` sobre el bucle de GTK de pywebview.
- Sondeo: `Poller`, con su hilo; avisa por `_on_update`.
- Latido: cada 15 s caduca terminales y refresca tooltip, tema e icono.
- Notificaciones: un bucle asyncio propio dentro de `Notifier`.
Las llamadas desde JS llegan en hilos de pywebview; el estado compartido va
protegido por `self._lock`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import webview

from pr_watch import (
    __version__,
    autostart,
    config,
    providers,
    settings_model,
    state_store,
    view,
)
from pr_watch.credential import CredentialStore, Source, Token, system_keyring
from pr_watch.inbox import Inbox
from pr_watch.notify import Notifier
from pr_watch.poller import Poller, Settings, Snapshot
from pr_watch.polling import State
from pr_watch.providers.base import (
    InvalidCredential,
    NetworkError,
    Provider,
    ProviderError,
    RateLimited,
    ScopeInaccessible,
)
from pr_watch.single_instance import Guard
from pr_watch.tray import Tray
from pr_watch.windows import (
    PANEL_WIDTH,
    SETTINGS_WIDTH,
    NativeWindow,
    PanelApi,
    PanelLogic,
    SettingsApi,
    push,
    ui_url,
)

_log = logging.getLogger(__name__)

HEARTBEAT_SECS = 15
_BG_DARK = "#2b2b2b"


class App:
    def __init__(self, config_dir: Path, guard: Guard) -> None:
        self.config_dir = config_dir
        self.config_path = config_dir / config.CONFIG_FILE
        self.guard = guard
        self._lock = threading.RLock()

        loaded = config.load(self.config_path)
        for w in loaded.warnings:
            _log.warning("config.toml: %s", w)
        self.cfg = loaded.config

        self.provider: Provider | None = None
        self.store: CredentialStore
        self.token: Token | None = None
        self.token_source: Source | None = None
        self.state_path: Path | None = None
        state = self._bind_forge()
        self.poller = Poller(
            self.provider, self._poll_settings(), state, self.state_path, self._on_update
        )
        self.snapshot: Snapshot = self.poller.snapshot()

        self.inbox = Inbox()
        self.logic = PanelLogic()
        self.notifier = Notifier(self.open_url, self.show_panel)
        # (clave de la forja, ambito, token escrito) que supero las dos
        # comprobaciones. Cambiar cualquiera de los tres la invalida.
        self.verified: tuple[str, str, str] | None = None
        self.settings_prompted = False
        self.panel_h = 420
        self.settings_h = 640
        self.panel_loaded = False
        self._quitting = False

        self.panel: Any = webview.create_window(
            "PR Watch",
            ui_url("panel.html"),
            js_api=PanelApi(self),
            width=PANEL_WIDTH,
            height=self.panel_h,
            frameless=True,
            easy_drag=False,
            on_top=True,
            hidden=True,
            resizable=False,
            background_color=_BG_DARK,
        )
        self.settings_window: Any = None
        self.autostart = autostart.Autostart()
        self.tray = Tray(
            on_toggle=self.toggle_panel,
            on_refresh=self.refresh,
            on_quit=self.quit,
            on_autostart=self.toggle_autostart,
            autostart_on=self.autostart.is_enabled,
            autostart_available=self.autostart.available,
        )

    # ---- arranque ----

    def run(self) -> None:
        # Solo el propio elemento marcado arrastra: asi el boton de cerrar
        # dentro de la cabecera de Ajustes sigue siendo un boton.
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
        webview.start(self._started, debug=bool(os.environ.get("PR_WATCH_DEVTOOLS")))

    def _started(self) -> None:
        NativeWindow(self.panel).hide_from_taskbar()
        self.tray.start()
        self.poller.start()
        self.guard.serve(self.show_panel)
        try:
            if self.autostart.refresh():
                _log.info("Autoarranque actualizado a la ruta actual")
        except OSError as e:
            _log.warning("No se pudo actualizar el autoarranque: %s", e)
        threading.Thread(target=self._heartbeat, name="heartbeat", daemon=True).start()
        self._refresh_ui()

    def _heartbeat(self) -> None:
        while not self._quitting:
            time.sleep(HEARTBEAT_SECS)
            self.poller.tick()
            self.snapshot = self.poller.snapshot()
            self._refresh_ui()
            # Si el usuario borro la entrada de autoarranque a mano, el menu
            # lo refleja: pystray solo evalua `checked` al reconstruirlo.
            try:
                self.tray.icon.update_menu()
            except Exception as e:
                _log.debug("No se pudo refrescar el menu: %s", e)

    # ---- forja activa ----

    def _bind_forge(self) -> State:
        """Ata proveedor, credencial y estado a la forja que dice la configuracion.

        Se llama al arrancar y cada vez que el usuario cambia de proveedor o
        de instancia: cada forja tiene su clave, y con ella su token y su
        estado guardados aparte.
        """
        self.provider = providers.create(self.cfg)
        key = self.provider.instance_key if self.provider else self.cfg.provider
        self.store = CredentialStore(key, self.config_dir, keyring_backend=system_keyring())
        found = self.store.load()
        self.token = found.token if found else None
        self.token_source = found.source if found else None
        if found:
            _log.info("Token de %s leido desde %s", key, found.source.value)
        self.state_path = (
            state_store.path_for(self.config_dir, key) if self.provider is not None else None
        )
        return state_store.load(self.state_path) if self.state_path else State()

    def _forge_provider(self, forge: settings_model.Forge) -> Provider | None:
        """El proveedor de la forja que la ventana tiene seleccionada."""
        if forge.provider == self.cfg.provider and forge.host == settings_model.host_of(self.cfg):
            return self.provider
        return providers.create(settings_model.apply_forge(self.cfg, forge))

    def _forge_token(self, provider: Provider | None) -> Token | None:
        """El token guardado de esa forja, que puede no ser la activa."""
        if provider is None:
            return None
        if self.provider is not None and provider.instance_key == self.provider.instance_key:
            return self.token
        store = CredentialStore(
            provider.instance_key, self.config_dir, keyring_backend=system_keyring()
        )
        found = store.load()
        return found.token if found else None

    def _poll_settings(self) -> Settings:
        return Settings(
            scope=self.cfg.scope(),
            token=self.token,
            interval=timedelta(seconds=self.cfg.poll_interval_secs),
            ttl=timedelta(minutes=self.cfg.closed_ttl_minutes),
        )

    # ---- datos -> interfaz ----

    def _on_update(self, snap: Snapshot) -> None:
        with self._lock:
            self.snapshot = snap
            self.inbox.add(snap.novelties)
        if snap.notices and self.cfg.notifications:
            self.notifier.emit(snap.notices)
        self._refresh_ui()

    def _vm(self) -> dict[str, Any]:
        return view.panel(
            self.snapshot,
            provider=self.provider,
            cfg=self.cfg,
            unseen=self.inbox.unseen_ids(),
            pinned=self.logic.pinned,
            now=datetime.now(UTC),
            version=__version__,
        )

    def _refresh_ui(self) -> None:
        if self._quitting:
            return
        tip = view.tooltip(self.snapshot, unseen_count=self.inbox.count, provider=self.provider)
        try:
            self.tray.update(unseen=self.inbox.count > 0, tooltip=tip)
        except Exception as e:
            _log.debug("No se pudo actualizar la bandeja: %s", e)
        if self.panel_loaded:
            push(self.panel, "render", self._vm())

    # ---- panel ----

    def panel_ready(self) -> None:
        self.panel_loaded = True
        push(self.panel, "render", self._vm())

    def toggle_panel(self) -> None:
        match self.logic.toggle(time.monotonic()):
            case "show":
                self.show_panel()
            case "hide":
                self.hide_panel()
            case _:
                pass

    def show_panel(self) -> None:
        with self._lock:
            if not self.logic.visible:
                self.inbox.panel_opened()
                self.logic.shown()
                push(self.panel, "render", self._vm())
                NativeWindow(self.panel).place((PANEL_WIDTH, self.panel_h), self.tray.icon)
                self.panel.show()
            NativeWindow(self.panel).front()
        self._refresh_ui()
        needs_setup = self.token is None or not self.cfg.scope()
        if needs_setup and not self.settings_prompted and self.provider is not None:
            self.settings_prompted = True
            self.open_settings()

    def hide_panel(self) -> None:
        with self._lock:
            if self.settings_window is not None:
                self.close_settings()
            self.panel.hide()
            self.logic.hidden()
            self.inbox.panel_closed()
        self._refresh_ui()

    def panel_blur(self, now: float) -> None:
        with self._lock:
            hide = self.logic.on_blur(now)
        if hide:
            self.hide_panel()

    def toggle_pin(self) -> None:
        with self._lock:
            self.logic.pinned = not self.logic.pinned
        self._refresh_ui()

    def panel_height(self, height: int) -> None:
        with self._lock:
            if height <= 0 or height == self.panel_h:
                return
            self.panel_h = height
            if self.logic.visible:
                NativeWindow(self.panel).place((PANEL_WIDTH, height), self.tray.icon)

    def refresh(self) -> None:
        if not self.poller.request_refresh():
            self.snapshot = self.poller.snapshot()
            self._refresh_ui()

    def open_url(self, url: str) -> None:
        if self.provider is None or not self.provider.allows_url(url):
            _log.warning("URL rechazada: no es del proveedor activo")
            return
        webbrowser.open(url)

    def open_create_token(self, forge: dict[str, Any]) -> None:
        """Abre la pagina de creacion de token de la forja seleccionada.

        La URL la construye el proveedor, no llega desde la ventana: asi
        tambien sirve para una forja a la que el usuario aun no ha cambiado.
        """
        provider = self._forge_provider(settings_model.forge_from(forge))
        destino = provider.descriptor.create_token_url if provider else ""
        if not destino:
            _log.warning("Sin pagina de creacion de token para esa forja")
            return
        webbrowser.open(destino)

    def toggle_autostart(self) -> None:
        wanted = not self.autostart.is_enabled()
        try:
            self.autostart.set_enabled(wanted)
            _log.info("Autoarranque %s", "activado" if wanted else "desactivado")
        except OSError as e:
            _log.warning("No se pudo cambiar el autoarranque: %s", e)
        self.tray.icon.update_menu()

    # ---- ajustes ----

    def open_settings(self) -> None:
        with self._lock:
            if self.settings_window is not None:
                self.settings_window.show()
                NativeWindow(self.settings_window).front()
                return
            self.logic.settings_open = True
            self.verified = None
            win: Any = webview.create_window(
                "PR Watch · Ajustes",
                ui_url("settings.html"),
                js_api=SettingsApi(self),
                width=SETTINGS_WIDTH,
                height=self.settings_h,
                frameless=True,
                easy_drag=False,
                on_top=True,
                resizable=False,
                background_color=_BG_DARK,
            )
            self.settings_window = win

        def shown() -> None:
            NativeWindow(win).place((SETTINGS_WIDTH, self.settings_h), None, near="center")
            NativeWindow(win).front()

        def closed() -> None:
            with self._lock:
                if self.settings_window is win:
                    self.settings_window = None
                    self.logic.settings_open = False
                    self.verified = None

        win.events.shown += shown
        win.events.closed += closed

    def close_settings(self) -> None:
        win = self.settings_window
        if win is not None:
            win.destroy()

    def settings_height(self, height: int) -> None:
        win = self.settings_window
        if win is not None and height > 0 and height != self.settings_h:
            self.settings_h = height
            NativeWindow(win).place((SETTINGS_WIDTH, height), None, near="center")

    def settings_load(self) -> dict[str, Any]:
        return settings_model.load(
            self.cfg,
            self.provider,
            has_token=self.token is not None,
            plaintext=self.token_source is Source.FILE,
            first_run=self.token is None,
        )

    def settings_verify_token(self, forge: dict[str, Any], token: str) -> dict[str, Any]:
        """Paso 1: el token por si solo, contra la forja seleccionada.

        Devuelve el usuario y los ambitos elegibles, nunca el token.
        """
        provider = self._forge_provider(settings_model.forge_from(forge))
        if provider is None:
            return {"ok": False, "kind": "network", "message": "esa forja no es utilizable"}
        candidate = Token(token) if token else self._forge_token(provider)
        if candidate is None:
            # `missing` distingue "aun no hay token" de "el token no vale":
            # al cambiar de forja no se pinta un error, se pide el token.
            return {"ok": False, "kind": "invalid", "missing": True, "message": "falta el token"}
        try:
            found = provider.list_scopes(candidate)
        except InvalidCredential as e:
            return {"ok": False, "kind": "invalid", "message": str(e)}
        except ScopeInaccessible as e:
            return {"ok": False, "kind": "scope", "message": str(e)}
        except RateLimited as e:
            return {"ok": False, "kind": "rate", "message": str(e)}
        except (NetworkError, ProviderError) as e:
            return {"ok": False, "kind": "network", "message": str(e) or type(e).__name__}
        return {
            "ok": True,
            "login": found.identity.login,
            "scopes": [{"value": s, "label": provider.scope_label(s)} for s in found.scopes],
        }

    def settings_verify(self, forge: dict[str, Any], scope: str, token: str) -> dict[str, Any]:
        """Paso 2: el ambito elegido, con el mismo token y la misma forja."""
        provider = self._forge_provider(settings_model.forge_from(forge))
        if provider is None:
            return {"ok": False, "kind": "network", "message": "esa forja no es utilizable"}
        candidate = Token(token) if token else self._forge_token(provider)
        if candidate is None:
            # `missing` distingue "aun no hay token" de "el token no vale":
            # al cambiar de forja no se pinta un error, se pide el token.
            return {"ok": False, "kind": "invalid", "missing": True, "message": "falta el token"}
        try:
            ident = provider.verify(scope, candidate)
        except InvalidCredential as e:
            return {"ok": False, "kind": "invalid", "message": str(e)}
        except ScopeInaccessible as e:
            return {"ok": False, "kind": "scope", "message": str(e)}
        except RateLimited as e:
            return {"ok": False, "kind": "rate", "message": str(e)}
        except (NetworkError, ProviderError) as e:
            return {"ok": False, "kind": "network", "message": str(e) or type(e).__name__}
        with self._lock:
            self.verified = (provider.instance_key, scope, token)
        return {"ok": True, "login": ident.login}

    def settings_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        parsed = settings_model.parse(self.cfg, payload)
        if parsed.error:
            return {"ok": False, "error": parsed.error}
        pendiente = self._forge_provider(parsed.forge)
        if pendiente is None:
            return {"ok": False, "error": "Esa forja no es utilizable: revisa la dirección."}
        needs_verify = settings_model.credential_changes(self.cfg, parsed) or self.token is None
        if needs_verify and self.verified != (pendiente.instance_key, parsed.scope, parsed.token):
            return {"ok": False, "error": "Verifica el token y el ámbito antes de guardar."}

        new_cfg = parsed.config.with_scope(parsed.scope)
        cambia_forja = settings_model.forge_changes(self.cfg, new_cfg)
        try:
            config.save(new_cfg, self.config_path)
        except OSError as e:
            _log.warning("No se pudo guardar config.toml: %s", e)
            return {"ok": False, "error": f"No se pudo guardar la configuración: {e}"}

        if cambia_forja:
            # El estado de la forja que se abandona se persiste antes de
            # soltarla; si no, lo ya visto alli se perderia.
            self.poller.save_now()
        with self._lock:
            turned_on = new_cfg.notifications and not self.cfg.notifications
            self.cfg = new_cfg
        state = self._bind_forge() if cambia_forja else None

        if parsed.token:
            token = Token(parsed.token)
            try:
                source = self.store.save(token)
            except OSError as e:
                return {"ok": False, "error": f"No se pudo guardar el token: {e}"}
            with self._lock:
                self.token = token
                self.token_source = source
        if turned_on:
            self.notifier.reset()

        if state is not None:
            _log.info("Forja activa: %s", new_cfg.provider)
            # Ni novedades ni notificaciones pendientes de la forja anterior:
            # el primer sondeo de la nueva no debe llegar como un aluvion.
            self.inbox.reset()
            self.notifier.reset()
            self.poller.rebind(self.provider, self._poll_settings(), state, self.state_path)
        else:
            self.poller.reconfigure(self._poll_settings())
        self.snapshot = self.poller.snapshot()
        self.close_settings()
        self._refresh_ui()
        return {"ok": True, "notes": parsed.notes}

    def settings_logout(self) -> dict[str, Any]:
        self.store.delete()
        with self._lock:
            self.token = None
            self.token_source = None
            self.verified = None
        self.poller.reconfigure(self._poll_settings())
        self._refresh_ui()
        return self.settings_load()

    def open_config_file(self) -> None:
        path = str(self.config_path)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as e:
            _log.warning("No se pudo abrir config.toml: %s", e)

    # ---- salida ----

    def quit(self) -> None:
        self._quitting = True
        self.poller.stop()
        self.poller.save_now()
        try:
            self.tray.stop()
        except Exception as e:
            _log.debug("Al retirar el icono: %s", e)
        self.close_settings()
        self.panel.destroy()
