import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from pr_watch import config
from pr_watch.credential import Token
from pr_watch.poller import Health
from pr_watch.providers.base import (
    Descriptor,
    Identity,
    InvalidCredential,
    ScopeInaccessible,
    ScopeList,
    Vocabulary,
)
from pr_watch.windows import REOPEN_GUARD_SECS, PanelLogic
from tests.test_credential import MemoryKeyring
from tests.test_poller import FakeProvider

GOOD = "github_pat_BUENO_0123456789"
FORGE = {"provider": "github", "host": ""}


class PanelLogicTest(unittest.TestCase):
    def test_perder_el_foco_lo_oculta(self) -> None:
        p = PanelLogic()
        p.shown()
        self.assertTrue(p.on_blur(10.0))

    def test_fijado_permanece(self) -> None:
        p = PanelLogic()
        p.shown()
        p.pinned = True
        self.assertFalse(p.on_blur(10.0))

    def test_con_ajustes_abiertos_no_se_escapa(self) -> None:
        p = PanelLogic()
        p.shown()
        p.settings_open = True
        self.assertFalse(p.on_blur(10.0))

    def test_el_fijado_no_se_hereda(self) -> None:
        p = PanelLogic()
        p.shown()
        p.pinned = True
        p.hidden()
        p.shown()
        self.assertFalse(p.pinned)

    def test_clic_en_el_icono_con_el_panel_abierto_lo_cierra_y_no_lo_reabre(self) -> None:
        p = PanelLogic()
        p.shown()
        # El clic en el icono quita el foco: se oculta...
        self.assertTrue(p.on_blur(100.0))
        p.hidden()
        # ...y el clic que llega justo despues no lo vuelve a abrir.
        self.assertEqual(p.toggle(100.1), "ignore")
        self.assertEqual(p.toggle(100.0 + REOPEN_GUARD_SECS + 0.1), "show")

    def test_alternar(self) -> None:
        p = PanelLogic()
        self.assertEqual(p.toggle(0.0), "show")
        p.shown()
        self.assertEqual(p.toggle(1.0), "hide")


class VerifyingProvider(FakeProvider):
    name = "github"
    instance_key = "github"

    def list_scopes(self, token: Token) -> ScopeList:
        if token.reveal() != GOOD:
            raise InvalidCredential("401")
        return ScopeList(Identity("miusuario"), ("Acme", "contoso"))

    def verify(self, scope: str, token: Token) -> Identity:
        if token.reveal() != GOOD:
            raise InvalidCredential("401")
        if scope != "contoso":
            raise ScopeInaccessible("sin acceso a " + scope)
        return Identity("miusuario")

    def allows_url(self, url: str) -> bool:
        return url.startswith("https://github.com/")


class SettingsFlowTest(unittest.TestCase):
    """La logica de Ajustes de App, con pywebview y la bandeja sustituidos."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.provider = VerifyingProvider()
        self.keyring = MemoryKeyring()
        patches = [
            mock.patch("pr_watch.app.webview"),
            mock.patch("pr_watch.app.Tray"),
            mock.patch("pr_watch.app.NativeWindow"),
            mock.patch("pr_watch.app.providers.create", return_value=self.provider),
            mock.patch("pr_watch.app.system_keyring", return_value=self.keyring),
            mock.patch.dict("os.environ", {}, clear=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        import os

        os.environ.pop("PR_WATCH_TOKEN", None)
        from pr_watch.app import App

        self.App = App

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def app(self) -> Any:
        a = self.App(self.dir, mock.Mock())
        a.store.cwd = self.dir  # sin .env del proyecto
        return a

    def payload(self, **kw: Any) -> dict[str, Any]:
        base = {
            "provider": "github",
            "host": "",
            "scope": "contoso",
            "token": GOOD,
            "poll_interval_secs": 60,
            "max_per_block": 5,
            "notifications": False,
        }
        base.update(kw)
        return base

    def test_primera_configuracion_completa(self) -> None:
        a = self.app()
        self.assertEqual(a.poller.health, Health.UNCONFIGURED)
        self.assertTrue(a.settings_load()["first_run"])
        self.assertFalse(a.settings_save(self.payload())["ok"])  # sin verificar
        self.assertEqual(
            a.settings_verify(FORGE, "contoso", GOOD), {"ok": True, "login": "miusuario"}
        )
        r = a.settings_save(self.payload())
        self.assertTrue(r["ok"])
        self.assertEqual(self.keyring.data[("pr-watch", "github")], GOOD)
        self.assertEqual(config.load(self.dir / "config.toml").config.github.org, "contoso")
        self.assertEqual(a.poller.health, Health.STARTING)  # empieza a sondear sin reiniciar

    def test_el_token_nunca_vuelve_a_la_ventana(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        a.settings_save(self.payload())
        self.assertNotIn(GOOD, repr(a.settings_load()))
        self.assertTrue(a.settings_load()["has_token"])

    def test_token_primero_devuelve_organizaciones_sin_el_token(self) -> None:
        a = self.app()
        r = a.settings_verify_token(FORGE, GOOD)
        self.assertEqual(
            r,
            {
                "ok": True,
                "login": "miusuario",
                "scopes": [
                    {"value": "Acme", "label": "Acme"},
                    {"value": "contoso", "label": "contoso"},
                ],
            },
        )
        self.assertEqual(a.settings_verify_token(FORGE, "malo-123456789")["kind"], "invalid")
        self.assertEqual(a.settings_verify_token(FORGE, "")["kind"], "invalid")  # nada guardado

    def test_token_guardado_se_verifica_sin_escribirlo(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        a.settings_save(self.payload())
        r = a.settings_verify_token(FORGE, "")
        self.assertTrue(r["ok"])
        self.assertNotIn(GOOD, repr(r))

    def test_errores_distinguidos(self) -> None:
        a = self.app()
        self.assertEqual(a.settings_verify(FORGE, "contoso", "malo-123456789")["kind"], "invalid")
        self.assertEqual(a.settings_verify(FORGE, "otra", GOOD)["kind"], "scope")
        self.assertEqual(a.settings_verify(FORGE, "contoso", "")["kind"], "invalid")

    def test_editar_tras_verificar_invalida(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        r = a.settings_save(self.payload(token=GOOD + "x"))
        self.assertFalse(r["ok"])

    def test_guardar_sin_token_conserva_el_guardado_y_aplica_el_resto(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        a.settings_save(self.payload())
        r = a.settings_save(self.payload(token="", max_per_block=50, poll_interval_secs=5))
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["notes"]), 2)
        self.assertEqual(a.cfg.max_per_block, 20)
        self.assertEqual(a.cfg.poll_interval_secs, 30)
        self.assertEqual(self.keyring.data[("pr-watch", "github")], GOOD)

    def test_error_de_disco_avisa_y_conserva(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        with mock.patch("pr_watch.app.config.save", side_effect=OSError("solo lectura")):
            r = a.settings_save(self.payload())
        self.assertFalse(r["ok"])
        self.assertIn("solo lectura", r["error"])
        self.assertIsNone(a.token)

    def test_cerrar_sesion(self) -> None:
        a = self.app()
        a.settings_verify(FORGE, "contoso", GOOD)
        a.settings_save(self.payload())
        data = a.settings_logout()
        self.assertFalse(data["has_token"])
        self.assertEqual(data["scope"], "contoso")
        self.assertEqual(self.keyring.data, {})
        self.assertEqual(a.poller.health, Health.UNCONFIGURED)

    def test_ajustes_una_vez_por_sesion_y_ventana_unica(self) -> None:
        a = self.app()
        with mock.patch.object(a, "open_settings", wraps=a.open_settings) as opened:
            a.show_panel()
            a.hide_panel()
            a.show_panel()
        self.assertEqual(opened.call_count, 1)
        first = a.settings_window
        a.open_settings()
        self.assertIs(a.settings_window, first)

    def test_cerrar_el_panel_cierra_los_ajustes(self) -> None:
        a = self.app()
        a.show_panel()
        win = a.settings_window
        self.assertIsNotNone(win)
        a.hide_panel()
        win.destroy.assert_called_once()

    def test_url_fuera_del_proveedor_se_rechaza(self) -> None:
        a = self.app()
        with mock.patch("pr_watch.app.webbrowser.open") as opened:
            a.open_url("https://evil.example/")
            a.open_url("https://github.com/contoso/x/pull/1")
        opened.assert_called_once_with("https://github.com/contoso/x/pull/1")


class GitLabProviderFake(VerifyingProvider):
    """Una segunda forja, con su propia clave de almacenamiento."""

    name = "gitlab"
    instance_key = "gitlab@gitlab-empresa-com"
    vocabulary = Vocabulary("MR", "!", "gitlab.empresa.com")
    descriptor = Descriptor(
        display_name="GitLab",
        scope_label="Grupo o espacio personal",
        scope_placeholder="Ruta del grupo",
        token_permissions=("read_api",),
        create_token_url="https://gitlab.empresa.com/-/user_settings/personal_access_tokens",
        configurable_host=True,
    )

    def verify(self, scope: str, token: Token) -> Identity:
        if token.reveal() != GITLAB_TOKEN:
            raise InvalidCredential("401")
        if scope != "empresa":
            raise ScopeInaccessible("sin acceso a " + scope)
        return Identity("miusuario")

    def list_scopes(self, token: Token) -> ScopeList:
        if token.reveal() != GITLAB_TOKEN:
            raise InvalidCredential("401")
        return ScopeList(Identity("miusuario"), ("user:miusuario", "empresa"))

    def allows_url(self, url: str) -> bool:
        return url.startswith("https://gitlab.empresa.com/")


GITLAB_TOKEN = "glpat-BUENO-0123456789"
GITLAB_FORGE = {"provider": "gitlab", "host": "https://gitlab.empresa.com"}


class ForgeSwitchTest(unittest.TestCase):
    """Cambiar de forja desde Ajustes, con la aplicacion en marcha."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.github = VerifyingProvider()
        self.gitlab = GitLabProviderFake()
        self.keyring = MemoryKeyring()

        def create(cfg: Any) -> Any:
            if cfg.provider == "gitlab":
                return self.gitlab if cfg.gitlab.host else None
            return self.github

        patches = [
            mock.patch("pr_watch.app.webview"),
            mock.patch("pr_watch.app.Tray"),
            mock.patch("pr_watch.app.NativeWindow"),
            mock.patch("pr_watch.app.providers.create", side_effect=create),
            mock.patch("pr_watch.app.system_keyring", return_value=self.keyring),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        import os

        os.environ.pop("PR_WATCH_TOKEN", None)
        from pr_watch.app import App

        a = App(self.dir, mock.Mock())
        a.store.cwd = self.dir
        self.a = a

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def payload(self, **kw: Any) -> dict[str, Any]:
        base = {
            "provider": "github",
            "host": "",
            "scope": "contoso",
            "token": GOOD,
            "poll_interval_secs": 60,
            "max_per_block": 5,
            "notifications": False,
        }
        base.update(kw)
        return base

    def gitlab_payload(self, **kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "provider": "gitlab",
            "host": "https://gitlab.empresa.com",
            "scope": "empresa",
            "token": GITLAB_TOKEN,
        }
        base.update(kw)
        return self.payload(**base)

    def configura_github(self) -> None:
        self.a.settings_verify(FORGE, "contoso", GOOD)
        self.a.settings_save(self.payload())

    def cambia_a_gitlab(self) -> dict[str, Any]:
        self.a.settings_verify(GITLAB_FORGE, "empresa", GITLAB_TOKEN)
        return self.a.settings_save(self.gitlab_payload())

    def test_cambio_de_forja_en_caliente(self) -> None:
        self.configura_github()
        self.assertIs(self.a.poller.provider, self.github)
        r = self.cambia_a_gitlab()
        self.assertTrue(r["ok"], r.get("error"))
        self.assertIs(self.a.poller.provider, self.gitlab)
        self.assertEqual(self.a.cfg.provider, "gitlab")
        self.assertEqual(self.a.cfg.gitlab.group, "empresa")
        self.assertEqual(self.a.poller.health, Health.STARTING)

    def test_cada_forja_guarda_su_token(self) -> None:
        self.configura_github()
        self.cambia_a_gitlab()
        self.assertEqual(self.keyring.data[("pr-watch", "github")], GOOD)
        self.assertEqual(self.keyring.data[("pr-watch", "gitlab@gitlab-empresa-com")], GITLAB_TOKEN)

    def test_el_panel_no_hereda_nada_de_la_anterior(self) -> None:
        self.configura_github()
        self.a.inbox.add([])
        self.a.inbox.count = 3
        self.a.inbox.marks.add("PR_1")
        self.cambia_a_gitlab()
        self.assertEqual(self.a.inbox.count, 0)
        self.assertEqual(self.a.inbox.unseen_ids(), set())
        self.assertEqual(self.a.poller.state.prs, {})

    def test_volver_recupera_token_y_ambito_sin_escribirlos(self) -> None:
        self.configura_github()
        self.cambia_a_gitlab()
        # De vuelta a GitHub: la ventana reverifica sola con el token
        # guardado de esa forja, sin que el usuario escriba nada.
        self.assertTrue(self.a.settings_verify_token(FORGE, "")["ok"])
        self.assertTrue(self.a.settings_verify(FORGE, "contoso", "")["ok"])
        r = self.a.settings_save(self.payload(token=""))
        self.assertTrue(r["ok"], r.get("error"))
        self.assertIs(self.a.poller.provider, self.github)
        assert self.a.token is not None
        self.assertEqual(self.a.token.reveal(), GOOD)
        self.assertEqual(self.a.cfg.scope(), "contoso")

    def test_cambiar_de_forja_sin_verificar_no_guarda(self) -> None:
        self.configura_github()
        r = self.a.settings_save(self.gitlab_payload(token=""))
        self.assertFalse(r["ok"])
        self.assertEqual(self.a.cfg.provider, "github")

    def test_la_verificacion_va_contra_la_forja_elegida(self) -> None:
        self.configura_github()
        # El token de GitHub no vale para GitLab.
        self.assertEqual(self.a.settings_verify(GITLAB_FORGE, "empresa", GOOD)["kind"], "invalid")
        self.assertTrue(self.a.settings_verify(GITLAB_FORGE, "empresa", GITLAB_TOKEN)["ok"])
        # Y el ambito de GitHub no existe en GitLab.
        self.assertEqual(
            self.a.settings_verify(GITLAB_FORGE, "contoso", GITLAB_TOKEN)["kind"], "scope"
        )

    def test_token_guardado_de_otra_forja_se_reutiliza(self) -> None:
        self.configura_github()
        self.cambia_a_gitlab()
        # Vuelta a la ventana con GitHub seleccionado: sin escribir el token.
        r = self.a.settings_verify_token(FORGE, "")
        self.assertTrue(r["ok"])
        self.assertNotIn(GOOD, repr(r))

    def test_sin_token_para_esa_forja_se_distingue(self) -> None:
        r = self.a.settings_verify_token(GITLAB_FORGE, "")
        self.assertFalse(r["ok"])
        self.assertTrue(r["missing"])

    def test_host_invalido_no_guarda(self) -> None:
        self.configura_github()
        r = self.a.settings_save(self.gitlab_payload(host="ftp://x"))
        self.assertFalse(r["ok"])
        self.assertEqual(self.a.cfg.provider, "github")

    def test_las_url_permitidas_son_las_de_la_forja_activa(self) -> None:
        self.configura_github()
        self.cambia_a_gitlab()
        with mock.patch("pr_watch.app.webbrowser.open") as opened:
            self.a.open_url("https://github.com/contoso/x/pull/1")
            self.a.open_url("https://gitlab.empresa.com/empresa/x/-/merge_requests/1")
        opened.assert_called_once_with("https://gitlab.empresa.com/empresa/x/-/merge_requests/1")

    def test_la_pagina_de_token_es_la_de_la_forja_elegida(self) -> None:
        with mock.patch("pr_watch.app.webbrowser.open") as opened:
            self.a.open_create_token(GITLAB_FORGE)
        destino = opened.call_args[0][0]
        self.assertTrue(destino.startswith("https://gitlab.empresa.com/"))

    def test_los_ajustes_describen_la_forja_activa(self) -> None:
        self.configura_github()
        self.cambia_a_gitlab()
        data = self.a.settings_load()
        self.assertEqual(data["provider"], "gitlab")
        self.assertEqual(data["noun"], "MR")
        self.assertEqual(data["host"], "https://gitlab.empresa.com")


if __name__ == "__main__":
    unittest.main()
