import tempfile
import tomllib
import unittest
from pathlib import Path

from pr_watch import config


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "config.toml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, text: str) -> None:
        self.path.write_text(text, "utf-8")

    def test_primera_ejecucion_crea_el_archivo_con_los_valores_por_defecto(self) -> None:
        r = config.load(self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(r.warnings, [])
        c = r.config
        self.assertEqual(c.provider, "github")
        self.assertEqual(c.github.org, "")
        self.assertEqual(c.poll_interval_secs, 60)
        self.assertEqual(c.max_per_block, 5)
        self.assertEqual(c.closed_ttl_minutes, 15)
        self.assertFalse(c.notifications)
        data = tomllib.loads(self.path.read_text("utf-8"))
        self.assertEqual(data["github"], {"org": "", "user": ""})

    def test_configuracion_ilegible_usa_valores_por_defecto_y_conserva_el_archivo(self) -> None:
        self.write("esto no es = = toml")
        r = config.load(self.path)
        self.assertFalse(r.file_ok)
        self.assertEqual(r.config, config.Config())
        self.assertEqual(len(r.warnings), 1)
        self.assertEqual(self.path.read_text("utf-8"), "esto no es = = toml")

    def test_clave_desconocida_se_ignora(self) -> None:
        self.write('cosa_rara = 3\npoll_interval_secs = 90\n[github]\norg = "contoso"\n')
        r = config.load(self.path)
        self.assertEqual(r.warnings, [])
        self.assertEqual(r.config.poll_interval_secs, 90)
        self.assertEqual(r.config.github.org, "contoso")

    def test_intervalo_por_debajo_del_suelo_se_eleva_y_avisa(self) -> None:
        self.write("poll_interval_secs = 5\n")
        r = config.load(self.path)
        self.assertEqual(r.config.poll_interval_secs, 30)
        self.assertEqual(len(r.warnings), 1)

    def test_tope_fuera_de_rango_se_ajusta_al_extremo(self) -> None:
        for raw, esperado in [(0, 1), (-4, 1), (21, 20), (500, 20)]:
            with self.subTest(raw=raw):
                self.write(f"max_per_block = {raw}\n")
                r = config.load(self.path)
                self.assertEqual(r.config.max_per_block, esperado)
                self.assertEqual(len(r.warnings), 1)

    def test_proveedor_desconocido_se_conserva_y_no_se_reescribe(self) -> None:
        self.write('provider = "bitbucket"\n')
        r = config.load(self.path)
        self.assertEqual(r.config.provider, "bitbucket")
        self.assertEqual(self.path.read_text("utf-8"), 'provider = "bitbucket"\n')

    def test_tipos_incorrectos_avisan_y_usan_el_valor_por_defecto(self) -> None:
        self.write('poll_interval_secs = "rapido"\nnotifications = "si"\n')
        r = config.load(self.path)
        self.assertEqual(r.config.poll_interval_secs, 60)
        self.assertFalse(r.config.notifications)
        self.assertEqual(len(r.warnings), 2)

    def test_guardar_y_releer(self) -> None:
        c = config.Config(poll_interval_secs=120, max_per_block=7, notifications=True)
        c.github.org = "contoso"
        config.save(c, self.path)
        self.assertEqual(config.load(self.path).config, c)

    def test_cuenta_personal(self) -> None:
        c = config.Config().with_scope("user:miusuario")
        self.assertEqual((c.github.user, c.github.org), ("miusuario", ""))
        self.assertEqual(c.scope(), "user:miusuario")
        config.save(c, self.path)
        self.assertEqual(config.load(self.path).config.scope(), "user:miusuario")
        # Y de vuelta a una organizacion, sin restos de la cuenta.
        self.assertEqual(c.with_scope("contoso").github.user, "")

    def test_organizacion_y_cuenta_a_la_vez_gana_la_organizacion(self) -> None:
        self.write('[github]\norg = "contoso"\nuser = "miusuario"\n')
        r = config.load(self.path)
        self.assertEqual(r.config.scope(), "contoso")
        self.assertEqual(len(r.warnings), 1)

    def test_scope_es_la_organizacion_en_github(self) -> None:
        c = config.Config().with_scope("  contoso ")
        self.assertEqual(c.scope(), "contoso")
        self.assertEqual(config.Config().scope(), "")


if __name__ == "__main__":
    unittest.main()
