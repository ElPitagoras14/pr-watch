import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from pr_watch import config
from pr_watch.credential import Token
from pr_watch.poller import Health
from pr_watch.providers.base import Identity, InvalidCredential, ScopeInaccessible, ScopeList
from pr_watch.windows import REOPEN_GUARD_SECS, PanelLogic
from tests.test_credential import MemoryKeyring
from tests.test_poller import FakeProvider

GOOD = "github_pat_BUENO_0123456789"


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
        self.assertEqual(a.settings_verify("contoso", GOOD), {"ok": True, "login": "miusuario"})
        r = a.settings_save(self.payload())
        self.assertTrue(r["ok"])
        self.assertEqual(self.keyring.data[("pr-watch", "github")], GOOD)
        self.assertEqual(config.load(self.dir / "config.toml").config.github.org, "contoso")
        self.assertEqual(a.poller.health, Health.STARTING)  # empieza a sondear sin reiniciar

    def test_el_token_nunca_vuelve_a_la_ventana(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
        a.settings_save(self.payload())
        self.assertNotIn(GOOD, repr(a.settings_load()))
        self.assertTrue(a.settings_load()["has_token"])

    def test_token_primero_devuelve_organizaciones_sin_el_token(self) -> None:
        a = self.app()
        r = a.settings_verify_token(GOOD)
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
        self.assertEqual(a.settings_verify_token("malo-123456789")["kind"], "invalid")
        self.assertEqual(a.settings_verify_token("")["kind"], "invalid")  # nada guardado

    def test_token_guardado_se_verifica_sin_escribirlo(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
        a.settings_save(self.payload())
        r = a.settings_verify_token("")
        self.assertTrue(r["ok"])
        self.assertNotIn(GOOD, repr(r))

    def test_errores_distinguidos(self) -> None:
        a = self.app()
        self.assertEqual(a.settings_verify("contoso", "malo-123456789")["kind"], "invalid")
        self.assertEqual(a.settings_verify("otra", GOOD)["kind"], "scope")
        self.assertEqual(a.settings_verify("contoso", "")["kind"], "invalid")

    def test_editar_tras_verificar_invalida(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
        r = a.settings_save(self.payload(token=GOOD + "x"))
        self.assertFalse(r["ok"])

    def test_guardar_sin_token_conserva_el_guardado_y_aplica_el_resto(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
        a.settings_save(self.payload())
        r = a.settings_save(self.payload(token="", max_per_block=50, poll_interval_secs=5))
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["notes"]), 2)
        self.assertEqual(a.cfg.max_per_block, 20)
        self.assertEqual(a.cfg.poll_interval_secs, 30)
        self.assertEqual(self.keyring.data[("pr-watch", "github")], GOOD)

    def test_error_de_disco_avisa_y_conserva(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
        with mock.patch("pr_watch.app.config.save", side_effect=OSError("solo lectura")):
            r = a.settings_save(self.payload())
        self.assertFalse(r["ok"])
        self.assertIn("solo lectura", r["error"])
        self.assertIsNone(a.token)

    def test_cerrar_sesion(self) -> None:
        a = self.app()
        a.settings_verify("contoso", GOOD)
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


if __name__ == "__main__":
    unittest.main()
