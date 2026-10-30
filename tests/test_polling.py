import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from pr_watch import polling, state_store
from pr_watch.polling import Kind, State, Tracked
from pr_watch.providers.base import (
    INACCESSIBLE,
    ChecksState,
    FetchResult,
    Inaccessible,
    PrState,
    PullRequest,
    Relation,
)
from tests.helpers import make_pr

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=15)


def poll(
    prev: State,
    prs: list[PullRequest],
    missing: dict[str, PrState | Inaccessible] | None = None,
    *,
    complete: bool = True,
    now: datetime = NOW,
) -> polling.Outcome:
    return polling.apply(prev, FetchResult(prs=prs, complete=complete), missing, now=now, ttl=TTL)


def kinds(outcome: polling.Outcome) -> list[tuple[str, Kind]]:
    return [(n.pr_id, n.kind) for n in outcome.novelties]


def base(*prs: PullRequest) -> State:
    return poll(State(), list(prs)).state


class NoveltyTest(unittest.TestCase):
    def test_primer_sondeo_fija_la_linea_base_sin_novedades(self) -> None:
        out = poll(State(), [make_pr(1), make_pr(2, relation=Relation.REVIEWER)])
        self.assertEqual(out.novelties, [])
        self.assertTrue(out.state.baseline)

    def test_aprobacion_nueva(self) -> None:
        s = base(make_pr(1, approvals=("ana",)))
        out = poll(s, [make_pr(1, approvals=("ana", "bea"))])
        self.assertEqual(kinds(out), [("PR_1", Kind.APPROVALS)])

    def test_cambio_irrelevante(self) -> None:
        s = base(make_pr(1))
        later = make_pr(1, updated_at=NOW, title="otro titulo")
        self.assertEqual(poll(s, [later]).novelties, [])

    def test_pr_nuevo_a_revisar(self) -> None:
        s = base(make_pr(1))
        out = poll(s, [make_pr(1), make_pr(2, relation=Relation.REVIEWER)])
        self.assertEqual(kinds(out), [("PR_2", Kind.NEW)])

    def test_cambios_pedidos_checks_conflictos_y_conversaciones(self) -> None:
        s = base(make_pr(1, checks=ChecksState.PENDING))
        new = make_pr(
            1, changes_requested=True, checks=ChecksState.FAILURE, conflicts=True, unresolved=2
        )
        self.assertEqual(
            [k for _, k in kinds(poll(s, [new]))],
            [Kind.CHANGES_REQUESTED, Kind.CHECKS_FAILED, Kind.CONFLICTS, Kind.UNRESOLVED],
        )

    def test_checks_pasan_a_correctos(self) -> None:
        s = base(make_pr(1, checks=ChecksState.FAILURE))
        out = poll(s, [make_pr(1, checks=ChecksState.SUCCESS)])
        self.assertEqual(kinds(out), [("PR_1", Kind.CHECKS_PASSED)])

    def test_conflicto_desconocido_conserva_el_anterior(self) -> None:
        s = base(make_pr(1, conflicts=True))
        out = poll(s, [make_pr(1, conflicts=None)])
        self.assertEqual(out.novelties, [])
        self.assertIs(out.state.prs["PR_1"].pr.conflicts, True)


class NoiseTest(unittest.TestCase):
    def test_borrador_oculto_y_sin_novedad(self) -> None:
        s = base(make_pr(1))
        out = poll(s, [make_pr(1), make_pr(2, draft=True)])
        self.assertEqual(out.novelties, [])
        self.assertEqual([t.pr.id for t in polling.visible(out.state)], ["PR_1"])

    def test_borrador_que_deja_de_serlo_es_nuevo(self) -> None:
        s = base(make_pr(2, draft=True))
        out = poll(s, [make_pr(2)])
        self.assertEqual(kinds(out), [("PR_2", Kind.NEW)])

    def test_fusionado_queda_visible_y_caduca(self) -> None:
        s = base(make_pr(1))
        out = poll(s, [], {"PR_1": PrState.MERGED})
        self.assertEqual(kinds(out), [("PR_1", Kind.MERGED)])
        t = out.state.prs["PR_1"]
        self.assertEqual(t.pr.state, PrState.MERGED)
        self.assertEqual(t.terminal_since, NOW)
        # Dentro del plazo sigue; pasado, desaparece sin novedad.
        still = poll(out.state, [], {}, now=NOW + timedelta(minutes=14))
        self.assertIn("PR_1", still.state.prs)
        gone = poll(out.state, [], {}, now=NOW + timedelta(minutes=15))
        self.assertNotIn("PR_1", gone.state.prs)
        self.assertEqual(gone.novelties, [])

    def test_cerrado(self) -> None:
        out = poll(base(make_pr(1)), [], {"PR_1": PrState.CLOSED})
        self.assertEqual(kinds(out), [("PR_1", Kind.CLOSED)])

    def test_caducidad_tras_reinicio(self) -> None:
        s = State(
            prs={
                "PR_1": Tracked(
                    make_pr(1, state=PrState.MERGED), terminal_since=NOW - timedelta(hours=1)
                )
            },
            baseline=True,
        )
        self.assertEqual(polling.expire(s, now=NOW, ttl=TTL).prs, {})

    def test_sale_de_la_relacion_sin_novedad(self) -> None:
        out = poll(base(make_pr(1)), [], {"PR_1": PrState.OPEN})
        self.assertEqual(out.novelties, [])
        self.assertNotIn("PR_1", out.state.prs)


class PurgeTest(unittest.TestCase):
    def test_se_pierde_el_acceso_purga_silenciosa(self) -> None:
        out = poll(base(make_pr(1), make_pr(2)), [make_pr(2)], {"PR_1": INACCESSIBLE})
        self.assertEqual(out.novelties, [])
        self.assertEqual(set(out.state.prs), {"PR_2"})

    def test_un_sondeo_incompleto_no_purga(self) -> None:
        s = base(make_pr(1), make_pr(2))
        out = poll(s, [make_pr(2)], None, complete=False)
        self.assertEqual(set(out.state.prs), {"PR_1", "PR_2"})
        self.assertEqual(out.novelties, [])

    def test_sin_estado_consultable_se_conserva(self) -> None:
        out = poll(base(make_pr(1)), [], None)
        self.assertIn("PR_1", out.state.prs)

    def test_se_recupera_el_acceso_vuelve_como_nuevo(self) -> None:
        purged = poll(base(make_pr(1)), [], {"PR_1": INACCESSIBLE}).state
        out = poll(purged, [make_pr(1)])
        self.assertEqual(kinds(out), [("PR_1", Kind.NEW)])

    def test_missing_ids(self) -> None:
        s = base(make_pr(1), make_pr(2), make_pr(3, draft=True))
        ids = polling.missing_ids(s, FetchResult(prs=[make_pr(2)], complete=True))
        self.assertEqual(ids, ["PR_1"])


class StateStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = state_store.path_for(Path(self._tmp.name), "github")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ida_y_vuelta(self) -> None:
        s = State(
            prs={
                "PR_1": Tracked(make_pr(1, approvals=("ana",), conflicts=None)),
                "PR_2": Tracked(
                    make_pr(2, state=PrState.MERGED, relation=Relation.ASSIGNEE),
                    terminal_since=NOW,
                    notified=frozenset({"ready"}),
                ),
            },
            baseline=True,
        )
        state_store.save(s, self.path)
        self.assertEqual(state_store.load(self.path), s)

    def test_no_avisar_dos_veces_tras_reiniciar(self) -> None:
        s = poll(base(make_pr(1)), [make_pr(1, approvals=("ana",))]).state
        state_store.save(s, self.path)
        again = poll(state_store.load(self.path), [make_pr(1, approvals=("ana",))])
        self.assertEqual(again.novelties, [])

    def test_sin_archivo_es_primer_arranque(self) -> None:
        self.assertEqual(state_store.load(self.path), State())

    def test_corrupto_se_descarta(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for raw in ["{no es json", "[]", json.dumps({"version": 99, "prs": []}), '{"version": 1}']:
            with self.subTest(raw=raw):
                self.path.write_text(raw, "utf-8")
                self.assertEqual(state_store.load(self.path), State())

    def test_escritura_atomica(self) -> None:
        state_store.save(base(make_pr(1)), self.path)
        before = self.path.read_text("utf-8")

        def boom(*_: Any) -> None:
            raise OSError("interrumpido")

        with mock.patch("pr_watch.state_store.os.replace", boom), self.assertRaises(OSError):
            state_store.save(base(make_pr(9)), self.path)
        self.assertEqual(self.path.read_text("utf-8"), before)


if __name__ == "__main__":
    unittest.main()
