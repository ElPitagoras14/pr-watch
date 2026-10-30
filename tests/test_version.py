import tomllib
import unittest
from pathlib import Path

import pr_watch


class VersionTest(unittest.TestCase):
    def test_paquete_y_pyproject_coinciden(self) -> None:
        # La version vive en dos sitios: el paquete (para el pie del panel y el
        # recurso del .exe) y pyproject.toml (para uv). Esto evita que diverjan.
        datos = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
        self.assertEqual(datos["project"]["version"], pr_watch.__version__)
