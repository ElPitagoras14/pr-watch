import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pr_watch import state_store
from pr_watch.credential import Token
from pr_watch.poller import Health, Poller, Settings, Snapshot
from pr_watch.polling import Kind, State
from pr_watch.providers.base import (
    FetchResult,
    Identity,
    Inaccessible,
    InvalidCredential,
    NetworkError,
    PrState,
    PullRequest,
    RateLimited,
    Relation,
    ScopeList,
    Vocabulary,
)
from tests.helpers import make_pr

TOKEN = Token("github_pat_PRUEBA_0123456789")


class FakeProvider:
    name = "fake"
    vocabulary = Vocabulary("PR", "#", "fake")

    def __init__(self) -> None:
        self.prs: list[PullRequest] = []
        self.complete = True
        self.error: Exception | None = None
        self.verify_error: Exception | None = None
        self.states: dict[str, PrState | Inaccessible] = {}
        self.fetches = 0
        self.gate: threading.Event | None = None

    def list_scopes(self, token: Token) -> ScopeList:
        if self.verify_error:
            raise self.verify_error
        return ScopeList(Identity("miusuario"), ("contoso",))

    def verify(self, scope: str, token: Token) -> Identity:
        if self.verify_error:
            raise self.verify_error
        return Identity("miusuario")

    def fetch_open(self, scope: str, token: Token) -> FetchResult:
        self.fetches += 1
        if self.gate is not None:
            self.gate.wait(5)
        if self.error:
            raise self.error
        return FetchResult(prs=list(self.prs), complete=self.complete)

    def fetch_states(self, ids: list[str], token: Token) -> dict[str, PrState | Inaccessible]:
        return {i: self.states[i] for i in ids if i in self.states}

    def block_url(self, scope: str, relations: tuple[Relation, ...]) -> str:
        return "https://fake/"

    def scope_label(self, scope: str) -> str:
        return scope

    def pr_ref(self, pr: PullRequest) -> str:
        return f"#{pr.number}"

    def allows_url(self, url: str) -> bool:
        return True


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t


def settings(token: Token | None = TOKEN, scope: str = "contoso") -> Settings:
    return Settings(
        scope=scope, token=token, interval=timedelta(seconds=60), ttl=timedelta(minutes=15)
    )


class PollerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state-fake.json"
        self.provider = FakeProvider()
        self.clock = Clock()
        self.updates: list[Snapshot] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def poller(self, s: Settings | None = None, state: State | None = None) -> Poller:
        return Poller(
            self.provider,
            s or settings(),
            state or State(),
            self.path,
            self.updates.append,
            now=self.clock,
        )

    def test_primer_sondeo_correcto(self) -> None:
        self.provider.prs = [make_pr(1)]
        p = self.poller()
        self.assertEqual(p.health, Health.STARTING)
        self.assertEqual(p.next_delay(), 60)
        self.assertTrue(p.poll_once())
        snap = self.updates[-1]
        self.assertEqual(snap.health, Health.OK)
        self.assertEqual(snap.login, "miusuario")
        self.assertEqual(snap.last_success, self.clock.t)
        self.assertEqual(snap.novelties, [])
        self.assertIn("PR_1", state_store.load(self.path).prs)

    def test_novedades_en_el_segundo_sondeo(self) -> None:
        p = self.poller()
        p.poll_once()
        self.provider.prs = [make_pr(2, relation=Relation.REVIEWER)]
        p.poll_once()
        self.assertEqual([n.kind for n in self.updates[-1].novelties], [Kind.NEW])

    def test_fallo_de_red_conserva_los_ultimos_datos(self) -> None:
        self.provider.prs = [make_pr(1)]
        p = self.poller()
        p.poll_once()
        ok_at = self.clock.t
        self.clock.t += timedelta(minutes=1)
        self.provider.error = NetworkError("timeout")
        p.poll_once()
        snap = self.updates[-1]
        self.assertEqual(snap.health, Health.STALE)
        self.assertEqual(snap.last_success, ok_at)
        self.assertIn("PR_1", snap.state.prs)
        # Sin reintento inmediato: espera al siguiente ciclo.
        self.assertEqual(p.next_delay(), 60)

    def test_limite_agotado_suspende_hasta_el_restablecimiento(self) -> None:
        p = self.poller()
        reset = self.clock.t + timedelta(minutes=10)
        self.provider.error = RateLimited(reset)
        p.poll_once()
        self.assertEqual(p.health, Health.RATE_LIMITED)
        self.assertEqual(p.next_delay(), 600)
        fetches = self.provider.fetches
        self.assertFalse(p.request_refresh())
        self.assertFalse(p.poll_once())
        self.assertEqual(self.provider.fetches, fetches)
        self.clock.t = reset
        self.provider.error = None
        self.assertTrue(p.poll_once())
        self.assertEqual(p.health, Health.OK)

    def test_credencial_invalida_deja_de_sondear(self) -> None:
        self.provider.verify_error = InvalidCredential("401")
        p = self.poller()
        p.poll_once()
        self.assertEqual(p.health, Health.INVALID_CREDENTIAL)
        self.assertIsNone(p.next_delay())
        self.assertFalse(p.request_refresh())

    def test_sin_token_no_sondea(self) -> None:
        p = self.poller(settings(token=None))
        self.assertEqual(p.health, Health.UNCONFIGURED)
        self.assertIsNone(p.next_delay())
        self.assertFalse(p.poll_once())
        self.assertEqual(self.provider.fetches, 0)

    def test_credencial_nueva_sin_reiniciar(self) -> None:
        p = self.poller(settings(token=None))
        p.reconfigure(settings())
        self.assertEqual(p.health, Health.STARTING)
        self.assertTrue(p.poll_once())
        self.assertEqual(p.health, Health.OK)

    def test_no_hay_sondeos_concurrentes(self) -> None:
        p = self.poller()
        self.provider.gate = threading.Event()
        t = threading.Thread(target=p.poll_once)
        t.start()
        while self.provider.fetches == 0:
            pass
        self.assertFalse(p.poll_once())
        self.provider.gate.set()
        t.join()
        self.assertEqual(self.provider.fetches, 1)

    def test_sondeo_incompleto_no_consulta_desaparecidos(self) -> None:
        self.provider.prs = [make_pr(1), make_pr(2)]
        p = self.poller()
        p.poll_once()
        self.provider.prs = [make_pr(2)]
        self.provider.complete = False
        p.poll_once()
        self.assertIn("PR_1", p.state.prs)

    def test_fusionado_via_estado_de_desaparecidos(self) -> None:
        self.provider.prs = [make_pr(1)]
        p = self.poller()
        p.poll_once()
        self.provider.prs = []
        self.provider.states = {"PR_1": PrState.MERGED}
        p.poll_once()
        self.assertEqual([n.kind for n in self.updates[-1].novelties], [Kind.MERGED])

    def test_proveedor_no_soportado(self) -> None:
        p = Poller(None, settings(), State(), None, self.updates.append, now=self.clock)
        self.assertEqual(p.health, Health.UNSUPPORTED)
        self.assertIsNone(p.next_delay())


if __name__ == "__main__":
    unittest.main()
