import io
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from pr_watch import __main__ as entry
from pr_watch import platform_check


def _en_linux(*, frozen: bool, glibc: str | None, gi: types.ModuleType | None) -> mock._patch_dict:  # type: ignore[type-arg]
    """Entorno simulado: plataforma, binario o fuente, glibc y modulo `gi`."""
    patches = mock.patch.multiple(sys, platform="linux")
    patches.start()
    if frozen:
        mock.patch.object(sys, "frozen", True, create=True).start()
    else:
        mock.patch.object(sys, "frozen", False, create=True).start()
    if glibc is None:
        mock.patch("os.confstr", side_effect=AttributeError, create=True).start()
    else:
        mock.patch("os.confstr", return_value=f"glibc {glibc}", create=True).start()
    # None en sys.modules hace que `import gi` lance ImportError.
    modulos: dict[str, types.ModuleType | None] = {"gi": gi}
    if gi is not None:
        modulos["gi.repository"] = types.ModuleType("gi.repository")
        for namespace, _, _ in platform_check.REQUIRED:
            modulos[f"gi.repository.{namespace}"] = types.ModuleType(namespace)
    return mock.patch.dict(sys.modules, modulos)


def _gi_falso(*, faltan: tuple[str, ...] = ()) -> types.ModuleType:
    gi = types.ModuleType("gi")

    def require_version(namespace: str, version: str) -> None:
        if namespace in faltan:
            raise ValueError(f"Namespace {namespace} not available")

    gi.require_version = require_version  # type: ignore[attr-defined]
    return gi


class PlatformCheckTest(unittest.TestCase):
    def tearDown(self) -> None:
        mock.patch.stopall()

    def test_binario_con_glibc_antigua(self) -> None:
        with _en_linux(frozen=True, glibc="2.31", gi=None):
            mensaje = platform_check.check()
        assert mensaje is not None
        self.assertIn("2.35", mensaje)
        self.assertIn("2.31", mensaje)
        self.assertIn("import of gi halted", mensaje)
        self.assertNotIn("python3-gi", mensaje)

    def test_binario_con_glibc_suficiente(self) -> None:
        with _en_linux(frozen=True, glibc="2.39", gi=None):
            mensaje = platform_check.check()
        assert mensaje is not None
        self.assertIn("import of gi halted", mensaje)
        self.assertNotIn("python3-gi", mensaje)
        self.assertNotIn("glibc", mensaje)

    def test_binario_sin_glibc_detectable(self) -> None:
        with _en_linux(frozen=True, glibc=None, gi=None):
            mensaje = platform_check.check()
        assert mensaje is not None
        self.assertIn("import of gi halted", mensaje)
        self.assertNotIn("python3-gi", mensaje)

    def test_fuente_sin_pygobject_recomienda_el_paquete(self) -> None:
        with _en_linux(frozen=False, glibc="2.39", gi=None):
            mensaje = platform_check.check()
        assert mensaje is not None
        self.assertIn("sudo apt install python3-gi", mensaje)

    def test_error_original_queda_en_el_log(self) -> None:
        with (
            _en_linux(frozen=True, glibc="2.31", gi=None),
            self.assertLogs("pr_watch.platform_check", "ERROR") as logs,
        ):
            platform_check.check()
        self.assertIn("import of gi halted", logs.output[0])

    def test_falta_una_biblioteca_de_gtk(self) -> None:
        gi = _gi_falso(faltan=("WebKit2",))
        with _en_linux(frozen=True, glibc="2.39", gi=gi):
            mensaje = platform_check.check()
        assert mensaje is not None
        self.assertIn("gir1.2-webkit2-4.1", mensaje)
        self.assertNotIn("gir1.2-gtk-3.0", mensaje)

    def test_todo_presente(self) -> None:
        with _en_linux(frozen=True, glibc="2.39", gi=_gi_falso()):
            self.assertIsNone(platform_check.check())

    def test_fuera_de_linux_no_comprueba_nada(self) -> None:
        with mock.patch.object(sys, "platform", "win32"):
            self.assertIsNone(platform_check.check())

    def test_glibc_version_se_interpreta(self) -> None:
        with mock.patch("os.confstr", return_value="glibc 2.35", create=True):
            self.assertEqual(platform_check.glibc_version(), (2, 35))
        with mock.patch("os.confstr", return_value="musl 1.2", create=True):
            self.assertIsNone(platform_check.glibc_version())


class CheckSystemTest(unittest.TestCase):
    def tearDown(self) -> None:
        mock.patch.stopall()

    def _correr(self, problema: str | None) -> tuple[int, str, str]:
        mock.patch.object(sys, "argv", ["pr-watch", "--check-system"]).start()
        mock.patch.object(entry.platform_check, "check", return_value=problema).start()
        mock.patch.object(entry.log, "setup").start()
        mock.patch.object(entry.config, "config_dir").start()
        guard = mock.patch.object(entry, "Guard").start()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            codigo = entry.main()
        guard.assert_not_called()
        return codigo, out.getvalue(), err.getvalue()

    def test_todo_en_orden_sale_con_cero(self) -> None:
        codigo, salida, _ = self._correr(None)
        self.assertEqual(codigo, 0)
        self.assertIn("completas", salida)

    def test_con_problema_sale_con_uno_y_lo_cuenta(self) -> None:
        codigo, _, error = self._correr("falta algo")
        self.assertEqual(codigo, 1)
        self.assertIn("falta algo", error)


if __name__ == "__main__":
    unittest.main()
