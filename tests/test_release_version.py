import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_version.py"


class ReleaseVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "pr_watch").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def escribir(self, pyproject: str, paquete: str) -> None:
        (self.dir / "pyproject.toml").write_text(
            f'[project]\nname = "pr-watch"\nversion = "{pyproject}"\n', "utf-8"
        )
        (self.dir / "pr_watch" / "__init__.py").write_text(
            f'"""doc."""\n\n__version__ = "{paquete}"\n', "utf-8"
        )

    def correr(
        self, raiz: Path | None = None, salida: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        # Como subproceso y no por import: es asi como lo invoca el pipeline.
        env = dict(os.environ)
        # Si estas pruebas corren dentro de Actions, el script heredaria el archivo
        # de salidas del paso real y escribiria en el. Cada caso decide el suyo.
        env.pop("GITHUB_OUTPUT", None)
        if salida is not None:
            env["GITHUB_OUTPUT"] = str(salida)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(raiz or self.dir)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_versiones_coincidentes_imprime_la_version(self) -> None:
        self.escribir("1.2.3", "1.2.3")
        r = self.correr()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "1.2.3")

    def test_escribe_la_version_en_la_salida_de_actions(self) -> None:
        self.escribir("1.2.3", "1.2.3")
        salida = self.dir / "github_output.txt"
        r = self.correr(salida=salida)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(salida.read_text("utf-8"), "version=1.2.3\n")

    def test_versiones_divergentes_falla_nombrando_ambas(self) -> None:
        self.escribir("1.2.3", "1.2.4")
        r = self.correr()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("1.2.3", r.stderr)
        self.assertIn("1.2.4", r.stderr)

    def test_version_mal_formada_falla_nombrando_el_valor(self) -> None:
        self.escribir("1.2.3rc1", "1.2.3rc1")
        r = self.correr()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("1.2.3rc1", r.stderr)

    def test_sin_dunder_version_falla(self) -> None:
        (self.dir / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', "utf-8")
        (self.dir / "pr_watch" / "__init__.py").write_text('"""doc."""\n', "utf-8")
        r = self.correr()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("__version__", r.stderr)

    def test_el_repositorio_real_tiene_una_version_valida(self) -> None:
        # Lo que el pipeline leera de verdad: si esto falla, no se publica nada.
        r = self.correr(ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        import pr_watch

        self.assertEqual(r.stdout.strip(), pr_watch.__version__)
