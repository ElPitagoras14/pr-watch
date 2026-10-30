import unittest

from pr_watch import settings_model
from pr_watch.config import Config
from pr_watch.providers.github import GitHubProvider
from pr_watch.providers.gitlab import GitLabProvider
from pr_watch.settings_model import Forge


def github_cfg() -> Config:
    return Config(provider="github").with_scope("contoso")


def gitlab_cfg(host: str = "https://gitlab.empresa.com") -> Config:
    cfg = Config(provider="gitlab")
    cfg.gitlab.host = host
    return cfg.with_scope("empresa/plataforma")


class LoadTest(unittest.TestCase):
    def test_los_textos_los_pone_el_proveedor_activo(self) -> None:
        github = settings_model.load(
            github_cfg(), GitHubProvider(), has_token=True, plaintext=False, first_run=False
        )
        gitlab = settings_model.load(
            gitlab_cfg(),
            GitLabProvider("https://gitlab.empresa.com"),
            has_token=True,
            plaintext=False,
            first_run=False,
        )
        self.assertEqual(github["scope_label"], "Cuenta u organización")
        self.assertEqual(github["noun"], "PR")
        self.assertIn("Pull requests", github["permissions"])
        self.assertFalse(github["configurable_host"])

        self.assertEqual(gitlab["scope_label"], "Grupo o espacio personal")
        self.assertEqual(gitlab["noun"], "MR")
        self.assertEqual(gitlab["permissions"], ["read_api"])
        self.assertTrue(gitlab["configurable_host"])
        self.assertEqual(gitlab["host"], "https://gitlab.empresa.com")

    def test_el_desplegable_describe_las_dos_forjas(self) -> None:
        data = settings_model.load(
            github_cfg(), GitHubProvider(), has_token=False, plaintext=False, first_run=True
        )
        por_nombre = {p["value"]: p for p in data["providers"]}
        self.assertEqual(set(por_nombre), {"github", "gitlab"})
        self.assertFalse(por_nombre["github"]["needs_host"])
        self.assertTrue(por_nombre["gitlab"]["needs_host"])
        # Aunque GitHub sea el activo, la ventana ya sabe que pide GitLab.
        self.assertEqual(por_nombre["gitlab"]["permissions"], ["read_api"])
        self.assertEqual(por_nombre["gitlab"]["noun"], "MR")

    def test_sin_proveedor_utilizable_la_ventana_se_dibuja_igual(self) -> None:
        cfg = Config(provider="gitlab")
        cfg.gitlab.host = ""  # host inservible
        data = settings_model.load(cfg, None, has_token=False, plaintext=False, first_run=True)
        self.assertEqual(data["provider"], "gitlab")
        self.assertTrue(data["configurable_host"])
        self.assertFalse(data["has_create_token_url"])

    def test_el_token_no_sale_hacia_la_ventana(self) -> None:
        data = settings_model.load(
            github_cfg(), GitHubProvider(), has_token=True, plaintext=True, first_run=False
        )
        self.assertNotIn("token", data)
        self.assertTrue(data["has_token"])
        self.assertIn("texto plano", data["plaintext_warning"] or "")


class ForgeTest(unittest.TestCase):
    def test_aplicar_una_forja_no_toca_la_vigente(self) -> None:
        base = github_cfg()
        nueva = settings_model.apply_forge(base, Forge("gitlab", "gitlab.empresa.com"))
        self.assertEqual(base.provider, "github")
        self.assertEqual(nueva.provider, "gitlab")
        self.assertEqual(nueva.gitlab.host, "https://gitlab.empresa.com")

    def test_gitlab_sin_host_asume_la_nube(self) -> None:
        nueva = settings_model.apply_forge(github_cfg(), Forge("gitlab", ""))
        self.assertEqual(nueva.gitlab.host, "https://gitlab.com")

    def test_host_solo_cuenta_en_la_forja_que_lo_usa(self) -> None:
        self.assertEqual(settings_model.host_of(github_cfg()), "")
        self.assertEqual(settings_model.host_of(gitlab_cfg()), "https://gitlab.empresa.com")

    def test_cambio_de_forja_detectado(self) -> None:
        github, gitlab = github_cfg(), gitlab_cfg()
        self.assertTrue(settings_model.forge_changes(github, gitlab))
        self.assertFalse(settings_model.forge_changes(github, github_cfg()))
        # Cambiar solo de instancia tambien es cambiar de forja.
        self.assertTrue(settings_model.forge_changes(gitlab, gitlab_cfg("https://gitlab.com")))

    def test_cambiar_de_forja_no_toca_los_ajustes_de_sondeo(self) -> None:
        base = github_cfg()
        base.poll_interval_secs = 120
        base.max_per_block = 9
        base.notifications = True
        nueva = settings_model.apply_forge(base, Forge("gitlab", ""))
        self.assertEqual(nueva.poll_interval_secs, 120)
        self.assertEqual(nueva.max_per_block, 9)
        self.assertTrue(nueva.notifications)


class ParseTest(unittest.TestCase):
    def payload(self, **kw: object) -> dict[str, object]:
        base: dict[str, object] = {
            "provider": "gitlab",
            "host": "https://gitlab.empresa.com",
            "scope": "empresa",
            "token": "",
            "poll_interval_secs": 60,
            "max_per_block": 5,
            "notifications": False,
        }
        base.update(kw)
        return base

    def test_host_invalido_no_deja_guardar(self) -> None:
        parsed = settings_model.parse(github_cfg(), self.payload(host="ftp://x"))
        self.assertTrue(parsed.error)

    def test_proveedor_no_implementado_se_conserva_el_actual(self) -> None:
        parsed = settings_model.parse(github_cfg(), self.payload(provider="bitbucket"))
        self.assertEqual(parsed.config.provider, "github")
        self.assertTrue(any("bitbucket" in n for n in parsed.notes))

    def test_intervalo_y_tope_se_corrigen(self) -> None:
        parsed = settings_model.parse(
            github_cfg(), self.payload(poll_interval_secs=5, max_per_block=50)
        )
        self.assertEqual(parsed.config.poll_interval_secs, 30)
        self.assertEqual(parsed.config.max_per_block, 20)
        self.assertEqual(len(parsed.notes), 2)

    def test_cambiar_de_forja_obliga_a_verificar(self) -> None:
        base = github_cfg()
        parsed = settings_model.parse(base, self.payload(scope=base.scope()))
        self.assertTrue(settings_model.credential_changes(base, parsed))

    def test_sin_cambios_no_obliga_a_verificar(self) -> None:
        base = gitlab_cfg()
        parsed = settings_model.parse(base, self.payload(scope=base.scope(), host=base.gitlab.host))
        self.assertFalse(settings_model.credential_changes(base, parsed))


if __name__ == "__main__":
    unittest.main()
