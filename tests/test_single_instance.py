import unittest
from unittest import mock

from pr_watch.single_instance import (
    AcquireResult,
    _classify_mutex_result,
    notify_user,
)

_ERROR_SUCCESS = 0
_ERROR_ALREADY_EXISTS = 183
_ERROR_ACCESS_DENIED = 5
_ERROR_OTHER = 1450  # ERROR_NO_SYSTEM_RESOURCES, cualquier otro codigo sirve


class ClassifyMutexResultTest(unittest.TestCase):
    """Logica pura de interpretar CreateMutexW/GetLastError (ver D14 y el bug real:

    GetLastError() llamado por separado de CreateMutexW es fragil porque ctypes
    puede ejecutar codigo entremedio que pise el codigo de error).
    """

    def test_handle_valido_sin_error_es_la_primera_instancia(self) -> None:
        self.assertEqual(
            _classify_mutex_result(12345, _ERROR_SUCCESS),
            AcquireResult.ACQUIRED,
        )

    def test_handle_valido_con_already_exists_es_instancia_existente(self) -> None:
        # El caso normal: el mutex ya existia, CreateMutexW igual nos da un
        # handle valido al objeto existente.
        self.assertEqual(
            _classify_mutex_result(12345, _ERROR_ALREADY_EXISTS),
            AcquireResult.ALREADY_RUNNING,
        )

    def test_handle_nulo_con_access_denied_es_instancia_existente(self) -> None:
        # El mutex lo creo un proceso con otro contexto de seguridad (p.ej.
        # elevado): no podemos abrirlo, pero sabemos que ya hay instancia.
        self.assertEqual(
            _classify_mutex_result(None, _ERROR_ACCESS_DENIED),
            AcquireResult.ALREADY_RUNNING,
        )

    def test_handle_nulo_con_otro_error_falla_cerrado(self) -> None:
        # Cualquier otro fallo al crear el mutex: mejor no arrancar una
        # segunda instancia sin garantia de unicidad.
        self.assertEqual(
            _classify_mutex_result(None, _ERROR_OTHER),
            AcquireResult.FAILED,
        )

    def test_handle_cero_se_trata_como_nulo(self) -> None:
        # Un handle de valor 0 tambien es falsy; no deberia confundirse con
        # un handle valido solo porque no es `None`.
        self.assertEqual(
            _classify_mutex_result(0, _ERROR_OTHER),
            AcquireResult.FAILED,
        )


class NotifyUserTest(unittest.TestCase):
    def test_en_linux_cae_a_stderr_y_log(self) -> None:
        with (
            mock.patch("pr_watch.single_instance.sys.platform", "linux"),
            mock.patch("pr_watch.single_instance._log") as log,
            mock.patch("builtins.print") as fake_print,
        ):
            notify_user("mensaje de prueba")
        log.error.assert_called_once()
        fake_print.assert_called_once()
        self.assertIn("mensaje de prueba", fake_print.call_args.args)

    def test_en_windows_llama_a_messageboxw(self) -> None:
        fake_user32 = mock.Mock()
        fake_windll = mock.Mock(user32=fake_user32)
        with (
            mock.patch("pr_watch.single_instance.sys.platform", "win32"),
            mock.patch("pr_watch.single_instance.ctypes.windll", fake_windll, create=True),
        ):
            notify_user("mensaje de prueba", title="pr-watch")
        fake_user32.MessageBoxW.assert_called_once()
        args = fake_user32.MessageBoxW.call_args.args
        self.assertEqual(args[1], "mensaje de prueba")
        self.assertEqual(args[2], "pr-watch")


if __name__ == "__main__":
    unittest.main()
