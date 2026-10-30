import unittest
from datetime import UTC, datetime, timedelta

from pr_watch import view
from pr_watch.config import Config
from pr_watch.poller import Health, Snapshot
from pr_watch.polling import State, Tracked
from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation
from pr_watch.providers.github import GitHubProvider
from tests.helpers import make_pr

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
GH = GitHubProvider(lambda *_: (_ for _ in ()).throw(AssertionError("sin red")))


def cfg(per_block: int = 5) -> Config:
    c = Config(max_per_block=per_block)
    c.github.org = "contoso"
    return c


def snap(*prs: PullRequest, health: Health = Health.OK, **kw: object) -> Snapshot:
    state = State(prs={p.id: Tracked(p) for p in prs}, baseline=True)
    base: dict[str, object] = {"login": "miusuario", "last_success": NOW}
    base.update(kw)
    return Snapshot(health=health, state=state, **base)  # type: ignore[arg-type]


def build(s: Snapshot, *, per_block: int = 5, unseen: set[str] | None = None) -> view.Json:
    return view.panel(
        s,
        provider=GH,
        cfg=cfg(per_block),
        unseen=unseen or set(),
        pinned=False,
        now=NOW,
        version="0.1.0",
    )


class StatusTest(unittest.TestCase):
    def label(self, pr: PullRequest, review: bool = False) -> tuple[str, str]:
        s = view.status(pr, in_review_block=review)
        return s.label, s.tone

    def test_prioridad(self) -> None:
        self.assertEqual(
            self.label(make_pr(approvals=("a",), conflicts=True)), ("conflictos", "red")
        )
        self.assertEqual(
            self.label(make_pr(checks=ChecksState.FAILURE, changes_requested=True)),
            ("checks fallidos", "red"),
        )
        self.assertEqual(
            self.label(make_pr(changes_requested=True, approvals=("a",))),
            ("cambios pedidos", "amber"),
        )
        self.assertEqual(
            self.label(make_pr(state=PrState.MERGED, conflicts=True)), ("fusionado", "gray")
        )
        self.assertEqual(self.label(make_pr(state=PrState.CLOSED)), ("cerrado", "gray"))
        self.assertEqual(
            self.label(make_pr(ready_to_merge=True, approvals=("a",))),
            ("listo para fusionar", "green"),
        )
        self.assertEqual(self.label(make_pr()), ("sin revisar", "amber"))

    def test_aprobaciones_sin_denominador(self) -> None:
        self.assertEqual(self.label(make_pr(approvals=("a", "b"))), ("aprobado (2)", "green"))

    def test_te_toca_solo_en_por_revisar(self) -> None:
        pr = make_pr(relation=Relation.REVIEWER, review_pending=True)
        self.assertEqual(self.label(pr, review=True), ("te toca", "amber"))
        self.assertEqual(self.label(pr, review=False), ("sin revisar", "amber"))


class PanelTest(unittest.TestCase):
    def test_dos_bloques_con_tope_por_bloque_y_total_real(self) -> None:
        prs = [make_pr(i) for i in range(1, 7)] + [
            make_pr(i, relation=Relation.REVIEWER) for i in range(11, 17)
        ]
        vm = build(snap(*prs), per_block=4)
        mine, review = vm["blocks"]
        self.assertEqual((mine["title"], mine["total"], len(mine["rows"])), ("MÍOS", 6, 4))
        self.assertEqual(
            (review["title"], review["total"], len(review["rows"])), ("POR REVISAR", 6, 4)
        )
        self.assertIn("author%3A%40me", mine["link"]["url"])
        self.assertIn("review-requested", review["link"]["url"])

    def test_los_accionables_entran_aunque_sean_antiguos(self) -> None:
        old = NOW - timedelta(days=30)
        broken = make_pr(1, conflicts=True, updated_at=old)
        fresh = [make_pr(i, updated_at=NOW - timedelta(minutes=i)) for i in range(2, 6)]
        rows = build(snap(broken, *fresh), per_block=2)["blocks"][0]["rows"]
        self.assertEqual(rows[0]["id"], "PR_1")
        self.assertEqual(rows[1]["id"], "PR_2")

    def test_fila_de_dos_lineas(self) -> None:
        mine = make_pr(142, title="Fix ruta", approvals=("bea", "ana"), checks=ChecksState.SUCCESS)
        rev = make_pr(
            150,
            relation=Relation.REVIEWER,
            review_pending=True,
            author="colega",
            repo="contoso/drivers",
            updated_at=NOW - timedelta(hours=3),
        )
        vm = build(snap(mine, rev), unseen={"PR_150"})
        r1 = vm["blocks"][0]["rows"][0]
        self.assertEqual(r1["ref"], "#142")
        self.assertEqual(r1["label"], "aprobado (2)")
        self.assertEqual(r1["sub"], "contoso/netops · checks ✓ · 0 sin resolver")
        self.assertEqual(r1["hover"], "Aprobado por bea, ana")
        self.assertFalse(r1["unseen"])
        r2 = vm["blocks"][1]["rows"][0]
        self.assertEqual(r2["label"], "te toca")
        self.assertEqual(r2["sub"], "contoso/drivers · de @colega · hace 3 h")
        self.assertTrue(r2["unseen"])

    def test_borradores_fuera(self) -> None:
        vm = build(snap(make_pr(1), make_pr(2, draft=True)))
        self.assertEqual(vm["blocks"][0]["total"], 1)

    def test_sin_nada_pendiente(self) -> None:
        vm = build(snap())
        self.assertEqual(vm["blocks"], [])
        self.assertEqual(vm["empty"], "No hay pull requests abiertos que te involucren.")

    def test_cuenta(self) -> None:
        rows = build(snap())["account"]
        self.assertEqual(
            [(r["label"], r["value"]) for r in rows],
            [
                ("Usuario", "miusuario"),
                ("Proveedor", "github.com · contoso"),
                ("Estado", "Conectado"),
            ],
        )

    def test_cuenta_personal_en_la_cuenta(self) -> None:
        vm = view.panel(
            snap(),
            provider=GH,
            cfg=Config().with_scope("user:miusuario"),
            unseen=set(),
            pinned=False,
            now=NOW,
            version="0.1.0",
        )
        self.assertEqual(vm["account"][1]["value"], "github.com · Cuenta personal")

    def test_sin_configurar_no_muestra_bloques_y_ofrece_ajustes(self) -> None:
        vm = build(snap(health=Health.UNCONFIGURED, login=None, last_success=None))
        self.assertEqual(vm["blocks"], [])
        self.assertIsNone(vm["empty"])
        self.assertEqual(vm["notice"]["action"]["action"], "settings")

    def test_desactualizado_conserva_datos_y_avisa_con_hora(self) -> None:
        vm = build(snap(make_pr(1), health=Health.STALE))
        self.assertEqual(vm["blocks"][0]["total"], 1)
        self.assertIn("desactualizados desde las", vm["notice"]["text"])

    def test_limite_agotado(self) -> None:
        vm = build(snap(health=Health.RATE_LIMITED, suspended_until=NOW + timedelta(minutes=5)))
        self.assertIn("agotado hasta las", vm["notice"]["text"])

    def test_pie(self) -> None:
        vm = build(snap(last_success=NOW - timedelta(seconds=12)))
        self.assertEqual(vm["footer"]["updated_text"], "Actualizado hace 12 s")
        self.assertEqual(vm["footer"]["version"], "0.1.0")


class TooltipTest(unittest.TestCase):
    def tip(self, s: Snapshot, unseen: int = 0) -> str:
        return view.tooltip(s, unseen_count=unseen, provider=GH)

    def test_con_novedades(self) -> None:
        self.assertEqual(self.tip(snap(make_pr(1)), 3), "pr-watch — 3 sin ver")

    def test_sin_novedades(self) -> None:
        t = self.tip(snap(make_pr(1), make_pr(2)))
        self.assertTrue(t.startswith("pr-watch — 2 PR vigilados · actualizado a las "))

    def test_desactualizado(self) -> None:
        self.assertIn("datos desactualizados desde", self.tip(snap(health=Health.STALE)))

    def test_sin_configurar(self) -> None:
        for h in (Health.UNCONFIGURED, Health.INVALID_CREDENTIAL):
            self.assertEqual(self.tip(snap(health=h)), "pr-watch — falta configurar: abre el panel")


if __name__ == "__main__":
    unittest.main()
