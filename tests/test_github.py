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
from pr_watch.providers.github import GitHubProvider, assert_read_only

FIXTURES = Path(__file__).parent / "fixtures" / "github"
TOKEN = Token("github_pat_PRUEBA_0123456789")


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


class ReadOnlyTest(unittest.TestCase):
    def test_una_mutacion_nunca_sale(self) -> None:
        t = FakeTransport()
        gh = GitHubProvider(t)
        with self.assertRaises(AssertionError):
            gh._send("mutation { addStar(input: {}) { clientMutationId } }", {}, TOKEN)
        self.assertEqual(t.calls, [])

    def test_subscription_tambien_se_rechaza(self) -> None:
        with self.assertRaises(AssertionError):
            assert_read_only("subscription X { y }")

    def test_la_palabra_en_cadenas_o_comentarios_no_cuenta(self) -> None:
        assert_read_only('query { search(query: "mutation") { issueCount } } # mutation')

    def test_el_token_va_en_la_cabecera_y_no_en_la_url(self) -> None:
        t = FakeTransport(ok(fixture("verify_ok.json")))
        GitHubProvider(t).verify("contoso", TOKEN)
        url, body, headers = t.calls[0]
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN.reveal()}")
        self.assertNotIn(TOKEN.reveal(), url)
        self.assertNotIn(TOKEN.reveal(), json.dumps(body))
        assert body is not None
        self.assertEqual(body["variables"], {"org": "contoso"})


class VerifyTest(unittest.TestCase):
    def test_credencial_valida(self) -> None:
        gh = GitHubProvider(FakeTransport(ok(fixture("verify_ok.json"))))
        self.assertEqual(gh.verify("contoso", TOKEN).login, "miusuario")

    def test_token_invalido(self) -> None:
        gh = GitHubProvider(FakeTransport(FakeResponse(401, {"message": "Bad credentials"})))
        with self.assertRaises(InvalidCredential):
            gh.verify("contoso", TOKEN)

    def test_organizacion_inexistente(self) -> None:
        gh = GitHubProvider(FakeTransport(ok(fixture("verify_no_org.json"))))
        with self.assertRaises(ScopeInaccessible):
            gh.verify("nada", TOKEN)

    def test_token_sin_acceso_a_repositorios_de_la_organizacion(self) -> None:
        gh = GitHubProvider(FakeTransport(ok(fixture("verify_no_repos.json"))))
        with self.assertRaises(ScopeInaccessible):
            gh.verify("contoso", TOKEN)

    def test_nombre_de_organizacion_invalido_no_llega_a_la_red(self) -> None:
        t = FakeTransport()
        with self.assertRaises(ScopeInaccessible):
            GitHubProvider(t).verify("contoso author:otro", TOKEN)
        self.assertEqual(t.calls, [])

    def test_limite_agotado(self) -> None:
        reset = 2_000_000_000
        resp = FakeResponse(
            403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}
        )
        with self.assertRaises(RateLimited) as cm:
            GitHubProvider(FakeTransport(resp)).verify("contoso", TOKEN)
        self.assertEqual(cm.exception.reset_at, datetime.fromtimestamp(reset, UTC))

    def test_limite_secundario_con_retry_after(self) -> None:
        resp = FakeResponse(429, {}, {"Retry-After": "60"})
        with self.assertRaises(RateLimited):
            GitHubProvider(FakeTransport(resp)).verify("contoso", TOKEN)

    def test_error_del_servidor(self) -> None:
        with self.assertRaises(NetworkError):
            GitHubProvider(FakeTransport(FakeResponse(502, {}))).verify("contoso", TOKEN)

    def test_red_caida(self) -> None:
        def down(*_: Any) -> FakeResponse:
            raise NetworkError("ConnectionError")

        with self.assertRaises(NetworkError):
            GitHubProvider(down).verify("contoso", TOKEN)


class ListScopesTest(unittest.TestCase):
    def test_organizaciones_paginadas_y_ordenadas(self) -> None:
        t = FakeTransport(ok(fixture("scopes_page1.json")), ok(fixture("scopes_page2.json")))
        r = GitHubProvider(t).list_scopes(TOKEN)
        self.assertEqual(r.identity.login, "miusuario")
        self.assertEqual(r.scopes, ("user:miusuario", "Acme", "beta-labs", "contoso"))
        self.assertEqual(t.body(1)["variables"], {"after": "O1"})

    def test_sin_organizaciones_ni_repositorios_no_es_error(self) -> None:
        t = FakeTransport(ok(fixture("scopes_empty.json")), ok([]))
        r = GitHubProvider(t).list_scopes(TOKEN)
        self.assertEqual(r.scopes, ("user:miusuario",))

    def test_fine_grained_deduce_la_organizacion_de_los_repositorios(self) -> None:
        t = FakeTransport(ok(fixture("scopes_empty.json")), ok(fixture("user_repos.json")))
        r = GitHubProvider(t).list_scopes(TOKEN)
        self.assertEqual(r.scopes, ("user:miusuario", "contoso"))
        url, body, headers = t.calls[1]
        self.assertIsNone(body)  # GET, sin cuerpo
        self.assertTrue(url.startswith("https://api.github.com/user/repos?"))
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN.reveal()}")

    def test_repositorios_paginados(self) -> None:
        full = [{"owner": {"login": f"org{i % 2}", "type": "Organization"}} for i in range(100)]
        last = [{"owner": {"login": "zeta", "type": "Organization"}}]
        t = FakeTransport(ok(fixture("scopes_empty.json")), ok(full), ok(last))
        r = GitHubProvider(t).list_scopes(TOKEN)
        self.assertEqual(r.scopes, ("user:miusuario", "org0", "org1", "zeta"))
        self.assertIn("page=2", t.calls[2][0])

    def test_con_organizaciones_no_mira_repositorios(self) -> None:
        t = FakeTransport(ok(fixture("scopes_page1.json")), ok(fixture("scopes_page2.json")))
        GitHubProvider(t).list_scopes(TOKEN)
        self.assertTrue(all(body is not None for _, body, _ in t.calls))

    def test_token_invalido(self) -> None:
        gh = GitHubProvider(FakeTransport(FakeResponse(401, {})))
        with self.assertRaises(InvalidCredential):
            gh.list_scopes(TOKEN)


class PersonalAccountTest(unittest.TestCase):
    def personal(self, login: str, total: int) -> FakeResponse:
        return ok({"data": {"viewer": {"login": login, "repositories": {"totalCount": total}}}})

    def test_verificar_la_cuenta_personal(self) -> None:
        t = FakeTransport(self.personal("miusuario", 7))
        self.assertEqual(GitHubProvider(t).verify("user:MiUsuario", TOKEN).login, "miusuario")

    def test_otra_cuenta_personal_no_vale(self) -> None:
        gh = GitHubProvider(FakeTransport(self.personal("miusuario", 7)))
        with self.assertRaises(ScopeInaccessible):
            gh.verify("user:otro", TOKEN)

    def test_sin_repositorios_personales(self) -> None:
        gh = GitHubProvider(FakeTransport(self.personal("miusuario", 0)))
        with self.assertRaises(ScopeInaccessible):
            gh.verify("user:miusuario", TOKEN)

    def test_busqueda_y_enlace_por_usuario(self) -> None:
        t = FakeTransport(
            ok(
                {
                    "data": {
                        a: {"pageInfo": {"hasNextPage": False}, "nodes": []}
                        for a in ("author", "reviewer", "assignee")
                    }
                }
            )
        )
        gh = GitHubProvider(t)
        gh.fetch_open("user:miusuario", TOKEN)
        variables = t.body(0)["variables"]
        self.assertTrue(variables["qa"].startswith("user:miusuario is:pr"))
        self.assertIn("user%3Amiusuario", gh.block_url("user:miusuario", (Relation.AUTHOR,)))
        self.assertEqual(gh.scope_label("user:miusuario"), "Cuenta personal")
        self.assertEqual(gh.scope_label("contoso"), "contoso")

    def test_nombre_invalido_no_llega_a_la_red(self) -> None:
        t = FakeTransport()
        with self.assertRaises(ScopeInaccessible):
            GitHubProvider(t).fetch_open("user:a b", TOKEN)
        self.assertEqual(t.calls, [])


class FetchOpenTest(unittest.TestCase):
    def fetch(self) -> tuple[GitHubProvider, FakeTransport, dict[str, Any]]:
        t = FakeTransport(ok(fixture("watch_page1.json")), ok(fixture("watch_page2.json")))
        gh = GitHubProvider(t)
        result = gh.fetch_open("contoso", TOKEN)
        self.assertTrue(result.complete)
        return gh, t, {p.id: p for p in result.prs}

    def test_tres_relaciones_unificadas_y_paginacion_por_alias(self) -> None:
        _, t, prs = self.fetch()
        self.assertEqual(set(prs), {"PR_142", "PR_131", "PR_150", "PR_160"})
        self.assertEqual(len(t.calls), 2)
        second = t.body(1)["variables"]
        self.assertEqual((second["ia"], second["ir"], second["is"]), (False, True, False))
        self.assertEqual(second["cr"], "R1")
        self.assertIn("org:contoso", second["qa"])
        self.assertIn("review-requested:@me", second["qr"])

    def test_un_pr_en_dos_relaciones_queda_con_la_de_mayor_prioridad(self) -> None:
        _, _, prs = self.fetch()
        self.assertEqual(prs["PR_142"].relation, Relation.AUTHOR)

    def test_aprobaciones_sin_denominador_y_ordenadas(self) -> None:
        _, _, prs = self.fetch()
        pr = prs["PR_142"]
        self.assertEqual(pr.approvals, ("Ana", "bea"))
        self.assertTrue(pr.ready_to_merge)
        self.assertEqual(pr.checks, ChecksState.SUCCESS)
        self.assertIs(pr.conflicts, False)
        self.assertEqual(pr.unresolved, 0)

    def test_roto(self) -> None:
        _, _, prs = self.fetch()
        pr = prs["PR_131"]
        self.assertTrue(pr.changes_requested)
        self.assertIs(pr.conflicts, True)
        self.assertEqual(pr.checks, ChecksState.FAILURE)
        self.assertEqual(pr.unresolved, 2)
        self.assertFalse(pr.ready_to_merge)

    def test_revision_pendiente_y_fusionabilidad_desconocida(self) -> None:
        _, _, prs = self.fetch()
        pr = prs["PR_150"]
        self.assertEqual(pr.relation, Relation.REVIEWER)
        self.assertTrue(pr.review_pending)
        self.assertIsNone(pr.conflicts)
        self.assertEqual(pr.checks, ChecksState.NONE)
        self.assertFalse(pr.ready_to_merge)

    def test_borrador_y_checks_en_curso(self) -> None:
        _, _, prs = self.fetch()
        pr = prs["PR_160"]
        self.assertTrue(pr.draft)
        self.assertEqual(pr.checks, ChecksState.PENDING)

    def test_desconocido_conserva_el_valor_anterior(self) -> None:
        gh = GitHubProvider(FakeTransport())
        base = fixture("watch_page1.json")["data"]["author"]["nodes"][1]
        self.assertIs(gh.translate(base, Relation.AUTHOR, review_pending=False).conflicts, True)
        unknown = dict(base, mergeable="UNKNOWN")
        self.assertIs(gh.translate(unknown, Relation.AUTHOR, review_pending=False).conflicts, True)

    def test_aprobacion_superada_por_cambios_pedidos(self) -> None:
        # latestOpinionatedReviews ya trae solo la ultima opinion de cada
        # revisor: si bea aprobo y despues pidio cambios, llega solo lo segundo.
        node = dict(
            fixture("watch_page1.json")["data"]["author"]["nodes"][0],
            reviewDecision="CHANGES_REQUESTED",
            latestOpinionatedReviews={
                "nodes": [{"state": "CHANGES_REQUESTED", "author": {"login": "bea"}}]
            },
        )
        pr = GitHubProvider(FakeTransport()).translate(node, Relation.AUTHOR, review_pending=False)
        self.assertEqual(pr.approvals, ())
        self.assertTrue(pr.changes_requested)
        self.assertFalse(pr.ready_to_merge)

    def test_sin_revision_obligatoria_hace_falta_al_menos_una_aprobacion(self) -> None:
        node = dict(
            fixture("watch_page1.json")["data"]["author"]["nodes"][0],
            reviewDecision=None,
            latestOpinionatedReviews={"nodes": []},
        )
        gh = GitHubProvider(FakeTransport())
        self.assertFalse(gh.translate(node, Relation.AUTHOR, review_pending=False).ready_to_merge)

    def test_una_relacion_fallida_marca_resultado_incompleto(self) -> None:
        body = fixture("watch_page1.json")
        body["data"]["assignee"] = None
        body["errors"] = [{"type": "FORBIDDEN", "path": ["assignee"], "message": "no"}]
        body["data"]["reviewer"]["pageInfo"]["hasNextPage"] = False
        result = GitHubProvider(FakeTransport(ok(body))).fetch_open("contoso", TOKEN)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual({p.id for p in result.prs}, {"PR_142", "PR_131", "PR_150"})

    def test_rate_limited_dentro_de_un_200(self) -> None:
        body = {"data": None, "errors": [{"type": "RATE_LIMITED", "message": "API rate limit"}]}
        resp = FakeResponse(200, body, {"x-ratelimit-reset": "2000000000"})
        with self.assertRaises(RateLimited):
            GitHubProvider(FakeTransport(resp)).fetch_open("contoso", TOKEN)


class StatesAndUrlsTest(unittest.TestCase):
    def test_fusionado_cerrado_e_inaccesible(self) -> None:
        gh = GitHubProvider(FakeTransport(ok(fixture("states.json"))))
        states = gh.fetch_states(["PR_1", "PR_2", "PR_3"], TOKEN)
        self.assertEqual(states["PR_1"], PrState.MERGED)
        self.assertEqual(states["PR_2"], PrState.CLOSED)
        self.assertIs(states["PR_3"], INACCESSIBLE)

    def test_urls(self) -> None:
        gh = GitHubProvider(FakeTransport())
        url = gh.block_url("contoso", (Relation.AUTHOR,))
        self.assertTrue(url.startswith("https://github.com/pulls?q="))
        self.assertIn("author%3A%40me", url)
        self.assertIn("review-requested", gh.block_url("contoso", (Relation.REVIEWER,)))
        self.assertTrue(gh.allows_url("https://github.com/contoso/x/pull/1"))
        self.assertFalse(gh.allows_url("https://evil.example/github.com/"))
        self.assertFalse(gh.allows_url("javascript:alert(1)"))


if __name__ == "__main__":
    unittest.main()
