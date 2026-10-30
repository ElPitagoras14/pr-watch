import sys
import tempfile
import unittest
from pathlib import Path

from pr_watch.autostart import Autostart

TEST_KEY = r"Software\pr-watch-test\Run"


class DesktopAutostartTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "autostart"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def auto(self, exe: str = "/opt/a/pr-watch", frozen: bool = True) -> Autostart:
        return Autostart(frozen=frozen, executable=exe, platform="linux", autostart_dir=self.dir)

    def test_apagado_por_defecto(self) -> None:
        a = self.auto()
        self.assertFalse(a.is_enabled())
        self.assertFalse(a.refresh())  # arrancar no lo crea
        self.assertFalse(self.dir.exists())

    def test_activar_y_desactivar(self) -> None:
        a = self.auto()
        a.set_enabled(True)
        self.assertTrue(a.is_enabled())
        self.assertIn('Exec="/opt/a/pr-watch"', a.desktop_file.read_text("utf-8"))
        a.set_enabled(False)
        self.assertFalse(a.is_enabled())
        a.set_enabled(False)  # desactivar dos veces no es error

    def test_borrado_a_mano_se_refleja(self) -> None:
        a = self.auto()
        a.enable()
        a.desktop_file.unlink()
        self.assertFalse(a.is_enabled())

    def test_la_ruta_cambio_se_actualiza_sin_duplicar(self) -> None:
        self.auto("/opt/a/pr-watch").enable()
        moved = self.auto("/opt/b/pr-watch")
        self.assertTrue(moved.refresh())
        self.assertFalse(moved.refresh())
        self.assertIn('Exec="/opt/b/pr-watch"', moved.desktop_file.read_text("utf-8"))
        self.assertEqual(len(list(self.dir.iterdir())), 1)

    def test_desde_el_codigo_no_se_ofrece(self) -> None:
        a = self.auto(frozen=False)
        self.assertFalse(a.available)
        with self.assertRaises(OSError):
            a.enable()
        self.assertFalse(self.dir.exists())

    def test_activacion_imposible_lanza_oserror(self) -> None:
        blocker = Path(self._tmp.name) / "archivo"
        blocker.write_text("no soy un directorio")
        a = Autostart(frozen=True, executable="/x", platform="linux", autostart_dir=blocker / "sub")
        with self.assertRaises(OSError):
            a.enable()
        self.assertFalse(a.is_enabled())


@unittest.skipUnless(sys.platform == "win32", "solo Windows")
class WindowsAutostartTest(unittest.TestCase):
    def tearDown(self) -> None:
        import winreg

        for sub in (TEST_KEY, r"Software\pr-watch-test"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass

    def auto(self, exe: str) -> Autostart:
        return Autostart(frozen=True, executable=exe, platform="win32", run_key=TEST_KEY)

    def test_activar_actualizar_y_desactivar(self) -> None:
        a = self.auto(r"C:\a\pr-watch.exe")
        self.assertFalse(a.is_enabled())
        self.assertFalse(a.refresh())
        a.enable()
        self.assertEqual(a.current(), r'"C:\a\pr-watch.exe"')
        moved = self.auto(r"C:\b\pr-watch.exe")
        self.assertTrue(moved.refresh())
        self.assertEqual(moved.current(), r'"C:\b\pr-watch.exe"')
        moved.disable()
        self.assertFalse(moved.is_enabled())
        moved.disable()


if __name__ == "__main__":
    unittest.main()
