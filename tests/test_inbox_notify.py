import unittest
from typing import Any

from pr_watch import notify
from pr_watch.inbox import Inbox
from pr_watch.polling import Kind, Novelty, State, Tracked
from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation
from tests.helpers import make_pr


def nov(*ids: str) -> list[Novelty]:
    return [Novelty(i, Kind.NEW) for i in ids]


class InboxTest(unittest.TestCase):
    def test_suma_por_novedad(self) -> None:
        box = Inbox()
        box.add(nov("a", "b", "c"))
        self.assertEqual(box.count, 3)
        self.assertEqual(box.unseen_ids(), {"a", "b", "c"})

    def test_abrir_el_panel_pone_a_cero_y_cerrarlo_limpia_las_marcas(self) -> None:
        box = Inbox()
        box.add(nov("a", "b", "c"))
        box.panel_opened()
        self.assertEqual(box.count, 0)
        self.assertEqual(box.unseen_ids(), {"a", "b", "c"})  # se ven mientras mira
        box.panel_closed()
        self.assertEqual(box.unseen_ids(), set())

    def test_novedad_con_el_panel_abierto_marca_pero_no_suma(self) -> None:
        box = Inbox()
        box.panel_opened()
        box.add(nov("a"))
        self.assertEqual(box.count, 0)
        self.assertEqual(box.unseen_ids(), {"a"})

    def test_novedad_con_el_panel_cerrado_suma(self) -> None:
        box = Inbox()
        box.panel_opened()
        box.panel_closed()
        box.add(nov("a"))
        self.assertEqual(box.count, 1)

    def test_arranca_en_cero(self) -> None:
        self.assertEqual(Inbox().count, 0)


def state(*prs: PullRequest, notified: dict[str, set[str]] | None = None) -> State:
    n = notified or {}
    return State(
        prs={p.id: Tracked(p, notified=frozenset(n.get(p.id, set()))) for p in prs},
        baseline=True,
    )


def run(s: State, record: bool = True) -> tuple[State, list[notify.Notice]]:
    return notify.evaluate(s, record=record, ref=lambda p: f"#{p.number}")


def mk(number: int, **kw: Any) -> PullRequest:
    return make_pr(number, **kw)


class NotifyTest(unittest.TestCase):
    def test_hechos(self) -> None:
        self.assertEqual(notify.facts(mk(1, ready_to_merge=True)), {"ready"})
        self.assertEqual(notify.facts(mk(1, conflicts=True)), {"broken"})
        self.assertEqual(notify.facts(mk(1, checks=ChecksState.FAILURE)), {"broken"})
        self.assertEqual(notify.facts(mk(1, changes_requested=True)), {"changes"})
        reviewer = mk(1, relation=Relation.REVIEWER, review_pending=True)
        self.assertEqual(notify.facts(reviewer), {"review"})
        # Lo no accionable no notifica.
        self.assertEqual(notify.facts(mk(1, unresolved=4)), set())
        self.assertEqual(notify.facts(mk(1, state=PrState.MERGED, ready_to_merge=True)), set())
        self.assertEqual(notify.facts(mk(1, relation=Relation.ASSIGNEE, conflicts=True)), set())

    def test_llega_algo_a_revisar(self) -> None:
        _, notes = run(
            state(mk(1, relation=Relation.REVIEWER, review_pending=True, title="Red"))
        )
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "Te piden revisión")
        self.assertTrue(notes[0].body.startswith("#1 Red"))
        self.assertEqual(notes[0].url, "https://github.com/contoso/netops/pull/1")

    def test_sin_repeticion(self) -> None:
        s, notes = run(state(mk(1, ready_to_merge=True)))
        self.assertEqual(len(notes), 1)
        s, notes = run(s)
        self.assertEqual(notes, [])

    def test_se_repite_tras_revertirse(self) -> None:
        s, notes = run(state(mk(1, conflicts=True)))
        self.assertEqual(len(notes), 1)
        s, notes = run(State(prs={"PR_1": Tracked(mk(1), notified=s.prs["PR_1"].notified)}))
        self.assertEqual(notes, [])
        s, notes = run(
            State(prs={"PR_1": Tracked(mk(1, conflicts=True), notified=s.prs["PR_1"].notified)})
        )
        self.assertEqual(len(notes), 1)

    def test_agrupacion(self) -> None:
        _, notes = run(state(*[mk(i, ready_to_merge=True) for i in range(1, 6)]))
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "pr-watch: 5 novedades")
        self.assertIsNone(notes[0].url)

    def test_linea_base_anota_sin_avisar(self) -> None:
        s, notes = run(state(mk(1, ready_to_merge=True)), record=False)
        self.assertEqual(notes, [])
        _, notes = run(s)
        self.assertEqual(notes, [])


class NotifierFailureTest(unittest.TestCase):
    def test_un_fallo_se_registra_una_vez_y_desactiva(self) -> None:
        n = notify.Notifier(lambda _: None, lambda: None)

        class Fut:
            def exception(self) -> Exception:
                return RuntimeError("sin servicio")

        with self.assertLogs("pr_watch.notify", level="WARNING") as logs:
            n._done(Fut())
            n._done(Fut())
        self.assertEqual(len(logs.records), 1)
        self.assertTrue(n.broken)
        n.reset()
        self.assertFalse(n.broken)


if __name__ == "__main__":
    unittest.main()
