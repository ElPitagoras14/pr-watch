import json
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pr_watch.credential import Token
from pr_watch.providers.base import (
    INACCESSIBLE,
    ChecksState,
    InvalidCredential,
    NetworkError,
    PrState,
    RateLimited,
    Relation,
    ScopeInaccessible,
)
from pr_watch.providers.gitlab import GitLabProvider, parse_scope, slug_for_host

FIXTURES = Path(__file__).parent / "fixtures" / "gitlab"
TOKEN = Token("glpat-PRUEBA-0123456789")
HOST = "https://gitlab.empresa.com"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeResponse:
    def __init__(self, status: int, body: Any, headers: Mapping[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self.headers: Mapping[str, str] = headers or {}

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeTransport:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, str]]] = []

    def __call__(
        self, url: str, body: dict[str, Any] | None, headers: dict[str, str], timeout: float
    ) -> FakeResponse:
        self.calls.append((url, body, headers))
        return self.responses.pop(0)

    def body(self, i: int) -> dict[str, Any]:
        b = self.calls[i][1]
        assert b is not None
        return b


def ok(body: Any) -> FakeResponse:
    return FakeResponse(200, body)


def provider(*responses: FakeResponse, host: str = HOST) -> GitLabProvider:
    return GitLabProvider(host, FakeTransport(*responses))


class InstanciaTest(unittest.TestCase):
    def test_la_nube_y_una_propia_solo_se_diferencian_en_el_host(self) -> None:
        nube = GitLabProvider("https://gitlab.com")
        propia = GitLabProvider(HOST)
        self.assertEqual(nube.api_url, "https://gitlab.com/api/graphql")
        self.assertEqual(propia.api_url, "https://gitlab.empresa.com/api/graphql")
        self.assertEqual(nube.vocabulary.noun, propia.vocabulary.noun)

    def test_instancia_en_subdirectorio(self) -> None:
        gl = GitLabProvider("https://devops.empresa.com/gitlab")
        self.assertEqual(gl.api_url, "https://devops.empresa.com/gitlab/api/graphql")

    def test_la_clave_distingue_instancias(self) -> None:
        self.assertEqual(GitLabProvider("https://gitlab.com").instance_key, "gitlab@gitlab-com")
        self.assertEqual(GitLabProvider(HOST).instance_key, "gitlab@gitlab-empresa-com")
        self.assertNotEqual(
            GitLabProvider("https://gitlab.com").instance_key, GitLabProvider(HOST).instance_key
        )

    def test_el_slug_sirve_como_nombre_de_archivo(self) -> None:
        self.assertEqual(
            slug_for_host("https://gitlab.empresa.com:8443/git"), "gitlab-empresa-com-8443-git"
        )

    def test_solo_se_abren_url_de_la_instancia(self) -> None:
        gl = GitLabProvider(HOST)
        self.assertTrue(gl.allows_url(HOST + "/empresa/x/-/merge_requests/1"))
        self.assertFalse(gl.allows_url("https://gitlab.com/empresa/x"))
        self.assertFalse(gl.allows_url("https://evil.example/"))

    def test_vocabulario_y_referencia(self) -> None:
        gl = GitLabProvider(HOST)
        self.assertEqual(gl.vocabulary.host_label, "gitlab.empresa.com")
        self.assertEqual(gl.descriptor.token_permissions, ("read_api",))
        self.assertIn(HOST, gl.descriptor.create_token_url)


class ReadOnlyTest(unittest.TestCase):
    def test_una_mutacion_nunca_sale(self) -> None:
        t = FakeTransport()
        gl = GitLabProvider(HOST, t)
        with self.assertRaises(AssertionError):
            gl._send("mutation { mergeRequestSetDraft(input: {}) { errors } }", {}, TOKEN)
        self.assertEqual(t.calls, [])

    def test_el_token_va_en_la_cabecera_y_el_ambito_como_variable(self) -> None:
        t = FakeTransport(ok(fixture("metadata.json")), ok(fixture("group.json")))
        GitLabProvider(HOST, t).verify("empresa", TOKEN)
        url, body, headers = t.calls[1]
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN.reveal()}")
        self.assertNotIn(TOKEN.reveal(), url)
        assert body is not None
        self.assertEqual(body["variables"], {"ruta": "empresa"})


class VersionTest(unittest.TestCase):
    def test_instancia_soportada(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("group.json")))
        self.assertEqual(gl.verify("empresa", TOKEN).login, "miusuario")

    def test_instancia_demasiado_antigua(self) -> None:
        gl = provider(ok(fixture("metadata_vieja.json")))
        with self.assertRaises(ScopeInaccessible) as e:
            gl.verify("empresa", TOKEN)
        self.assertIn("15.11.3", str(e.exception))
        self.assertIn("16.0", str(e.exception))

    def test_sin_version_se_continua(self) -> None:
        gl = provider(ok(fixture("metadata_sin_version.json")), ok(fixture("group.json")))
        self.assertEqual(gl.verify("empresa", TOKEN).login, "miusuario")

    def test_campo_que_la_instancia_no_tiene(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("campo_inexistente.json")))
        with self.assertRaises(NetworkError) as e:
            gl.verify("empresa", TOKEN)
        self.assertIn("changeRequesters", str(e.exception))
        self.assertIn("19.2.7", str(e.exception))


class ScopesTest(unittest.TestCase):
    def test_espacio_personal_primero_y_grupos_por_ruta(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("scopes.json")))
        found = gl.list_scopes(TOKEN)
        self.assertEqual(found.identity.login, "miusuario")
        self.assertEqual(found.scopes, ("user:miusuario", "empresa", "empresa/plataforma/red"))

    def test_token_sin_grupos_no_es_error(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("scopes_sin_grupos.json")))
        self.assertEqual(gl.list_scopes(TOKEN).scopes, ("user:miusuario",))

    def test_token_invalido(self) -> None:
        gl = provider(FakeResponse(401, {"message": "401 Unauthorized"}))
        with self.assertRaises(InvalidCredential):
            gl.list_scopes(TOKEN)

    def test_el_identificador_del_grupo_viene_con_la_lista(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("scopes.json")))
        gl.list_scopes(TOKEN)
        self.assertEqual(gl._group_ids["empresa"], "gid://gitlab/Group/44")


class VerifyTest(unittest.TestCase):
    def test_grupo_inaccesible(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("group_inaccesible.json")))
        with self.assertRaises(ScopeInaccessible):
            gl.verify("secreto", TOKEN)

    def test_espacio_personal_propio(self) -> None:
        gl = provider(ok(fixture("metadata.json")))
        self.assertEqual(gl.verify("user:miusuario", TOKEN).login, "miusuario")

    def test_espacio_personal_de_otro(self) -> None:
        gl = provider(ok(fixture("metadata.json")))
        with self.assertRaises(ScopeInaccessible):
            gl.verify("user:otro", TOKEN)

    def test_ruta_invalida_no_llega_a_la_red(self) -> None:
        t = FakeTransport()
        with self.assertRaises(ScopeInaccessible):
            GitLabProvider(HOST, t).verify("con espacios/", TOKEN)
        self.assertEqual(t.calls, [])

    def test_subgrupos_en_la_ruta(self) -> None:
        self.assertEqual(parse_scope("empresa/plataforma/red"), ("group", "empresa/plataforma/red"))
        self.assertEqual(parse_scope("user:miusuario"), ("user", "miusuario"))
        with self.assertRaises(ScopeInaccessible):
            parse_scope("user:miusuario/sub")

    def test_host_que_no_es_gitlab(self) -> None:
        gl = provider(FakeResponse(404, {"error": "not found"}))
        with self.assertRaises(NetworkError) as e:
            gl.list_scopes(TOKEN)
        self.assertIn("direccion", str(e.exception))


class FetchOpenTest(unittest.TestCase):
    def fetch(self, scope: str = "empresa") -> Any:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify(scope, TOKEN)
        return gl, gl.fetch_open(scope, TOKEN)

    def test_tres_relaciones_y_paginacion(self) -> None:
        _, result = self.fetch()
        self.assertTrue(result.complete)
        por_id = {pr.number: pr for pr in result.prs}
        self.assertEqual(sorted(por_id), [101, 102, 103, 104, 105, 106])

    def test_un_mr_en_dos_relaciones_gana_la_prioritaria(self) -> None:
        _, result = self.fetch()
        dos = [pr for pr in result.prs if pr.number == 102]
        self.assertEqual(len(dos), 1)  # una sola vez, no una por relacion
        self.assertEqual(dos[0].relation, Relation.AUTHOR)

    def test_el_grupo_viaja_como_identificador_global(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify("empresa", TOKEN)
        gl.fetch_open("empresa", TOKEN)
        transporte = gl._transport
        assert isinstance(transporte, FakeTransport)
        self.assertEqual(transporte.body(2)["variables"]["gid"], "gid://gitlab/Group/44")
        self.assertEqual(transporte.body(2)["variables"]["n"], 50)

    def test_subgrupos_incluidos(self) -> None:
        _, result = self.fetch()
        anidado = next(pr for pr in result.prs if pr.number == 104)
        self.assertEqual(anidado.repo, "empresa/plataforma/red")

    def test_ambito_personal_filtra_lo_que_no_es_suyo(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify("user:miusuario", TOKEN)
        result = gl.fetch_open("user:miusuario", TOKEN)
        repos = {pr.repo for pr in result.prs}
        self.assertEqual(repos, {"miusuario/apuntes"})

    def test_ambito_personal_no_manda_grupo(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify("user:miusuario", TOKEN)
        gl.fetch_open("user:miusuario", TOKEN)
        transporte = gl._transport
        assert isinstance(transporte, FakeTransport)
        self.assertIsNone(transporte.body(1)["variables"]["gid"])

    def test_una_relacion_falla_y_el_resultado_es_incompleto(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_parcial.json")),
        )
        gl.verify("empresa", TOKEN)
        result = gl.fetch_open("empresa", TOKEN)
        self.assertFalse(result.complete)
        self.assertTrue(any("revisor" in e for e in result.errors))


class TraduccionTest(unittest.TestCase):
    def prs(self) -> dict[int, Any]:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_estados.json")),
        )
        gl.verify("empresa", TOKEN)
        return {pr.number: pr for pr in gl.fetch_open("empresa", TOKEN).prs}

    def test_campos_basicos(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify("empresa", TOKEN)
        pr = next(p for p in gl.fetch_open("empresa", TOKEN).prs if p.number == 101)
        self.assertEqual(pr.id, "gid://gitlab/MergeRequest/101")
        self.assertEqual(pr.repo, "empresa/plataforma")
        self.assertEqual(pr.author, "miusuario")
        self.assertEqual(pr.state, PrState.OPEN)
        self.assertEqual(pr.approvals, ("ana", "bea"))
        self.assertEqual(pr.checks, ChecksState.SUCCESS)
        self.assertEqual(pr.unresolved, 2)
        self.assertTrue(pr.ready_to_merge)
        self.assertEqual(pr.updated_at, datetime.fromisoformat("2026-10-20T12:00:32-05:00"))

    def test_revision_pendiente_del_usuario(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_page1.json")),
            ok(fixture("watch_page2.json")),
        )
        gl.verify("empresa", TOKEN)
        prs = {p.number: p for p in gl.fetch_open("empresa", TOKEN).prs}
        self.assertTrue(prs[105].review_pending)  # sin revisar
        self.assertFalse(prs[106].review_pending)  # ya revisado
        self.assertFalse(prs[101].review_pending)  # ni siquiera es revisor

    def test_sin_pipeline_los_checks_son_ninguno(self) -> None:
        self.assertEqual(self.prs()[203].checks, ChecksState.NONE)

    def test_cambios_pedidos_desde_el_estado_del_revisor(self) -> None:
        pr = self.prs()[202]
        self.assertTrue(pr.changes_requested)
        self.assertFalse(pr.ready_to_merge)
        self.assertEqual(pr.checks, ChecksState.FAILURE)
        self.assertTrue(pr.conflicts)

    def test_fusionabilidad_sin_calcular_conserva_lo_anterior(self) -> None:
        gl = GitLabProvider(HOST)
        nodo = {
            "id": "gid://gitlab/MergeRequest/9",
            "iid": "9",
            "mergeStatusEnum": "CHECKING",
            "conflicts": True,
        }
        self.assertIsNone(gl.translate(nodo, Relation.AUTHOR, "miusuario").conflicts)
        gl.known_conflicts["gid://gitlab/MergeRequest/9"] = False
        self.assertFalse(gl.translate(nodo, Relation.AUTHOR, "miusuario").conflicts)

    def test_aprobado_sin_regla_de_aprobacion(self) -> None:
        # `approved` llega en false, pero hay un aprobador: cuenta como aprobado.
        pr = self.prs()[203]
        self.assertEqual(pr.approvals, ("bea",))
        self.assertTrue(pr.ready_to_merge)

    def test_borrador_no_esta_listo(self) -> None:
        pr = self.prs()[201]
        self.assertTrue(pr.draft)
        self.assertFalse(pr.ready_to_merge)
        self.assertEqual(pr.checks, ChecksState.PENDING)

    def test_referencia_con_admiracion(self) -> None:
        gl = GitLabProvider(HOST)
        pr = gl.translate({"id": "x", "iid": "142"}, Relation.AUTHOR, "miusuario")
        self.assertEqual(gl.pr_ref(pr), "!142")


class EstadosTest(unittest.TestCase):
    def test_fusionado_cerrado_e_inaccesible_en_un_lote(self) -> None:
        gl = provider(ok(fixture("estados.json")))
        ids = [f"gid://gitlab/MergeRequest/{n}" for n in (1, 2, 3)]
        estados = gl.fetch_states(ids, TOKEN)
        self.assertEqual(estados[ids[0]], PrState.MERGED)
        self.assertEqual(estados[ids[1]], PrState.CLOSED)
        self.assertEqual(estados[ids[2]], INACCESSIBLE)

    def test_quince_identificadores_son_una_peticion(self) -> None:
        ids = [f"gid://gitlab/MergeRequest/{n}" for n in range(15)]
        cuerpo = {"data": {f"m{i}": {"id": v, "state": "merged"} for i, v in enumerate(ids)}}
        t = FakeTransport(ok(cuerpo))
        GitLabProvider(HOST, t).fetch_states(ids, TOKEN)
        self.assertEqual(len(t.calls), 1)


class LimitesTest(unittest.TestCase):
    def test_limite_con_cabecera(self) -> None:
        reset = int(datetime(2026, 10, 30, 12, 0, tzinfo=UTC).timestamp())
        gl = provider(FakeResponse(429, {}, {"RateLimit-Reset": str(reset)}))
        with self.assertRaises(RateLimited) as e:
            gl.list_scopes(TOKEN)
        self.assertEqual(e.exception.reset_at, datetime.fromtimestamp(reset, UTC))

    def test_limite_sin_cabecera_espera_un_margen(self) -> None:
        gl = provider(FakeResponse(429, {}))
        with self.assertRaises(RateLimited) as e:
            gl.list_scopes(TOKEN)
        self.assertGreater(e.exception.reset_at, datetime.now(UTC))

    def test_error_de_servidor(self) -> None:
        gl = provider(FakeResponse(503, {}))
        with self.assertRaises(NetworkError):
            gl.list_scopes(TOKEN)

    def test_rechazo_por_complejidad(self) -> None:
        cuerpo = {"errors": [{"message": "Query has complexity of 300, which exceeds max"}]}
        gl = provider(ok(cuerpo))
        with self.assertRaises(NetworkError) as e:
            gl.list_scopes(TOKEN)
        self.assertIn("compleja", str(e.exception))

    def test_el_sondeo_avisa_al_acercarse_al_techo(self) -> None:
        gl = provider(
            ok(fixture("metadata.json")),
            ok(fixture("group.json")),
            ok(fixture("watch_estados.json")),
        )
        gl.verify("empresa", TOKEN)
        with self.assertLogs("pr_watch.providers.gitlab", level="WARNING") as logs:
            gl.fetch_open("empresa", TOKEN)
        self.assertIn("210", "".join(logs.output))


class UrlTest(unittest.TestCase):
    def test_url_de_bloque_por_grupo(self) -> None:
        gl = provider(ok(fixture("metadata.json")), ok(fixture("group.json")))
        gl.verify("empresa", TOKEN)
        url = gl.block_url("empresa", (Relation.AUTHOR,))
        self.assertTrue(url.startswith(HOST + "/groups/empresa/-/merge_requests?"))
        self.assertIn("author_username=miusuario", url)

    def test_url_de_bloque_personal(self) -> None:
        gl = provider(ok(fixture("metadata.json")))
        gl.verify("user:miusuario", TOKEN)
        url = gl.block_url("user:miusuario", (Relation.REVIEWER,))
        self.assertTrue(url.startswith(HOST + "/dashboard/merge_requests?"))
        self.assertIn("reviewer_username=miusuario", url)

    def test_etiqueta_del_ambito(self) -> None:
        gl = GitLabProvider(HOST)
        self.assertEqual(gl.scope_label("user:miusuario"), "Espacio personal")
        self.assertEqual(gl.scope_label("empresa/plataforma"), "empresa/plataforma")


if __name__ == "__main__":
    unittest.main()
