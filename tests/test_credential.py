import logging
import sys
import tempfile
import unittest
from pathlib import Path

from pr_watch import credential, log
from pr_watch.credential import CredentialStore, Source, Token

SECRET = "github_pat_11SECRETO_QUE_NO_DEBE_SALIR"


class MemoryKeyring:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.data[(service, username)]


class BrokenKeyring(MemoryKeyring):
    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError("sin backend")


class CredentialTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.cfg = root / "cfg"
        self.cwd = root / "cwd"
        self.cwd.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def store(
        self,
        kr: credential.KeyringBackend | None,
        env: dict[str, str] | None = None,
    ) -> CredentialStore:
        return CredentialStore(
            "github", self.cfg, cwd=self.cwd, environ=env or {}, keyring_backend=kr
        )

    def test_token_no_se_deja_imprimir(self) -> None:
        t = Token(SECRET)
        self.assertNotIn(SECRET, repr(t))
        self.assertNotIn(SECRET, str(t))
        self.assertNotIn(SECRET, f"{t}")
        self.assertEqual(t.reveal(), SECRET)

    def test_el_entorno_tiene_prioridad_sobre_el_keyring(self) -> None:
        kr = MemoryKeyring()
        kr.set_password("pr-watch", "github", "del-keyring-xxxxxxxx")
        loaded = self.store(kr, {"PR_WATCH_TOKEN": SECRET}).load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.ENV)
        self.assertEqual(loaded.token.reveal(), SECRET)

    def test_github_token_y_gh_token_se_ignoran(self) -> None:
        env = {"GITHUB_TOKEN": "ghp_escritura1234", "GH_TOKEN": "ghp_escritura5678"}
        self.assertIsNone(self.store(MemoryKeyring(), env).load())

    def test_dotenv(self) -> None:
        (self.cwd / ".env").write_text(f'OTRA=1\nPR_WATCH_TOKEN="{SECRET}"\n', "utf-8")
        loaded = self.store(MemoryKeyring()).load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.DOTENV)
        self.assertEqual(loaded.token.reveal(), SECRET)

    def test_guardar_y_leer_del_keyring(self) -> None:
        kr = MemoryKeyring()
        s = self.store(kr)
        self.assertEqual(s.save(Token(SECRET)), Source.KEYRING)
        self.assertEqual(kr.data[("pr-watch", "github")], SECRET)
        loaded = s.load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.KEYRING)
        self.assertFalse(s.fallback_file.exists())

    def test_sin_keyring_cae_a_archivo(self) -> None:
        s = self.store(None)
        self.assertEqual(s.save(Token(SECRET)), Source.FILE)
        self.assertEqual(s.fallback_file.read_text("utf-8"), SECRET)
        if sys.platform != "win32":
            self.assertEqual(s.fallback_file.stat().st_mode & 0o777, 0o600)
        loaded = s.load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.FILE)

    def test_keyring_que_falla_al_escribir_cae_a_archivo(self) -> None:
        s = self.store(BrokenKeyring())
        self.assertEqual(s.save(Token(SECRET)), Source.FILE)

    def test_si_aparece_el_keyring_se_migra_desde_el_archivo(self) -> None:
        self.store(None).save(Token(SECRET))
        kr = MemoryKeyring()
        s = self.store(kr)
        loaded = s.load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.KEYRING)
        self.assertEqual(kr.data[("pr-watch", "github")], SECRET)
        self.assertFalse(s.fallback_file.exists())

    def test_borrar_keyring_y_archivo(self) -> None:
        kr = MemoryKeyring()
        s = self.store(kr)
        s.save(Token(SECRET))
        self.store(None).save(Token(SECRET))  # deja tambien el archivo
        s.delete()
        self.assertEqual(kr.data, {})
        self.assertFalse(s.fallback_file.exists())
        self.assertIsNone(s.load())
        self.assertFalse(s.has_stored())

    def test_borrar_sin_nada_no_es_error(self) -> None:
        self.store(MemoryKeyring()).delete()
        self.store(None).delete()

    def test_borrar_no_toca_la_configuracion(self) -> None:
        self.cfg.mkdir(parents=True)
        cfg_file = self.cfg / "config.toml"
        cfg_file.write_text('[github]\norg = "contoso"\n', "utf-8")
        s = self.store(MemoryKeyring())
        s.save(Token(SECRET))
        s.delete()
        self.assertEqual(cfg_file.read_text("utf-8"), '[github]\norg = "contoso"\n')


class LogRedactionTest(unittest.TestCase):
    def test_el_token_no_llega_al_archivo_de_registro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = log.setup(Path(tmp))
            token = Token(SECRET)
            logger = logging.getLogger("prueba")
            logger.error("token %s", token)
            logger.error("crudo %s", token.reveal())
            try:
                raise ValueError(f"fallo con {token.reveal()}")
            except ValueError:
                logger.exception("excepcion")
            for h in logging.getLogger().handlers:
                h.flush()
            text = path.read_text("utf-8")
            for h in list(logging.getLogger().handlers):
                if getattr(h, "baseFilename", "") == str(path):
                    logging.getLogger().removeHandler(h)
                    h.close()
        self.assertNotIn(SECRET, text)
        self.assertIn("<oculto>", text)


class ClavePorInstanciaTest(unittest.TestCase):
    """Cada forja guarda lo suyo: dos instancias no se pisan el token."""

    NUBE = "gitlab@gitlab-com"
    PROPIA = "gitlab@gitlab-empresa-com"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.cfg = root / "cfg"
        self.cwd = root / "cwd"
        self.cwd.mkdir()
        self.kr = MemoryKeyring()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def store(self, key: str, env: dict[str, str] | None = None) -> CredentialStore:
        return CredentialStore(
            key, self.cfg, cwd=self.cwd, environ=env or {}, keyring_backend=self.kr
        )

    def test_dos_instancias_no_se_pisan(self) -> None:
        self.store(self.NUBE).save(Token("glpat-nube-0123456789"))
        self.store(self.PROPIA).save(Token("glpat-propia-9876543210"))
        nube = self.store(self.NUBE).load()
        propia = self.store(self.PROPIA).load()
        assert nube is not None and propia is not None
        self.assertEqual(nube.token.reveal(), "glpat-nube-0123456789")
        self.assertEqual(propia.token.reveal(), "glpat-propia-9876543210")

    def test_borrar_una_no_toca_la_otra(self) -> None:
        self.store(self.NUBE).save(Token("glpat-nube-0123456789"))
        self.store("github").save(Token("github_pat_0123456789"))
        self.store(self.NUBE).delete()
        self.assertIsNone(self.store(self.NUBE).load())
        self.assertIsNotNone(self.store("github").load())

    def test_la_clave_de_github_no_cambio(self) -> None:
        # Lo guardado antes de este cambio se sigue encontrando.
        self.kr.set_password("pr-watch", "github", SECRET)
        loaded = self.store("github").load()
        assert loaded is not None
        self.assertEqual(loaded.token.reveal(), SECRET)

    def test_archivo_de_respaldo_por_instancia(self) -> None:
        self.assertNotEqual(
            self.store(self.NUBE).fallback_file, self.store(self.PROPIA).fallback_file
        )

    def test_variable_propia_de_la_forja(self) -> None:
        self.assertEqual(
            credential.env_var_for(self.PROPIA), "PR_WATCH_TOKEN_GITLAB_GITLAB_EMPRESA_COM"
        )
        env = {"PR_WATCH_TOKEN_GITLAB_GITLAB_EMPRESA_COM": SECRET}
        loaded = self.store(self.PROPIA, env).load()
        assert loaded is not None
        self.assertEqual(loaded.token.reveal(), SECRET)
        # La de otra instancia no sirve para esta.
        self.assertIsNone(self.store(self.NUBE, env).load())

    def test_la_propia_gana_a_la_generica(self) -> None:
        env = {
            "PR_WATCH_TOKEN": "generico-0123456789",
            "PR_WATCH_TOKEN_GITLAB_GITLAB_EMPRESA_COM": SECRET,
        }
        loaded = self.store(self.PROPIA, env).load()
        assert loaded is not None
        self.assertEqual(loaded.token.reveal(), SECRET)

    def test_la_generica_sigue_valiendo(self) -> None:
        loaded = self.store(self.PROPIA, {"PR_WATCH_TOKEN": SECRET}).load()
        assert loaded is not None
        self.assertEqual(loaded.token.reveal(), SECRET)

    def test_en_el_dotenv_tambien_manda_la_propia(self) -> None:
        (self.cwd / ".env").write_text(
            "PR_WATCH_TOKEN=generico-0123456789\n"
            f"PR_WATCH_TOKEN_GITLAB_GITLAB_EMPRESA_COM={SECRET}\n",
            "utf-8",
        )
        loaded = self.store(self.PROPIA).load()
        assert loaded is not None
        self.assertEqual(loaded.source, Source.DOTENV)
        self.assertEqual(loaded.token.reveal(), SECRET)


if __name__ == "__main__":
    unittest.main()
