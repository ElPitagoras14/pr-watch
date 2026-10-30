"""Vista previa de la interfaz en un navegador, sin token ni red (D16).

`uv run python -m pr_watch.preview` genera los escenarios pasando modelos de
ejemplo por `view.py` (los mismos que usa la aplicacion, asi que no pueden
desincronizarse) y sirve `pr_watch/ui/` en localhost.
"""

from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pr_watch import __version__, settings_model, view
from pr_watch.config import Config
from pr_watch.poller import Health, Snapshot
from pr_watch.polling import State, Tracked
from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation
from pr_watch.providers.github import GitHubProvider
from pr_watch.providers.gitlab import GitLabProvider

UI_DIR = Path(__file__).parent / "ui"
SCENARIOS_FILE = UI_DIR / "preview" / "scenarios.json"


def _pr(number: int, title: str, **kw: Any) -> PullRequest:
    repo = kw.pop("repo", "contoso/netops")
    base: dict[str, Any] = {
        "id": f"PR_{number}",
        "repo": repo,
        "number": number,
        "title": title,
        "url": f"https://github.com/{repo}/pull/{number}",
        "author": "miusuario",
        "state": PrState.OPEN,
        "draft": False,
        "relation": Relation.AUTHOR,
        "approvals": (),
        "changes_requested": False,
        "checks": ChecksState.SUCCESS,
        "conflicts": False,
        "unresolved": 0,
        "ready_to_merge": False,
        "review_pending": False,
        "updated_at": datetime.now(UTC) - timedelta(hours=number % 7),
    }
    base.update(kw)
    return PullRequest(**base)


def _mine() -> list[PullRequest]:
    return [
        _pr(142, "Fix ruta estática en el balanceador", approvals=("ana", "bea")),
        _pr(138, "Refactor de rutas", checks=ChecksState.PENDING, unresolved=2),
        _pr(
            131,
            "Logs de auditoría",
            repo="contoso/audit",
            conflicts=True,
            checks=ChecksState.FAILURE,
        ),
    ]


def _review() -> list[PullRequest]:
    return [
        _pr(
            150,
            "Utilidades de red",
            repo="contoso/drivers",
            relation=Relation.REVIEWER,
            review_pending=True,
            author="colega",
            checks=ChecksState.NONE,
        ),
    ]


def _all_states() -> list[PullRequest]:
    return [
        _pr(1, "Listo para fusionar", approvals=("ana",), ready_to_merge=True),
        _pr(2, "Aprobado sin checks verdes", approvals=("ana", "bea"), checks=ChecksState.PENDING),
        _pr(3, "Cambios pedidos", changes_requested=True, unresolved=4),
        _pr(4, "Checks fallidos", checks=ChecksState.FAILURE),
        _pr(
            5,
            "Conflictos con un título lo bastante largo para que se trunque al ancho",
            conflicts=True,
        ),
        _pr(6, "Fusionado hace un momento", state=PrState.MERGED, approvals=("ana",)),
        _pr(7, "Cerrado", state=PrState.CLOSED),
        _pr(8, "Sin revisar", checks=ChecksState.NONE),
        _pr(
            20, "Te toca revisar", relation=Relation.REVIEWER, review_pending=True, author="colega"
        ),
        _pr(
            21, "Asignado, aprobado", relation=Relation.ASSIGNEE, approvals=("bea",), author="otro"
        ),
    ]


def _snap(prs: list[PullRequest], health: Health = Health.OK, **kw: Any) -> Snapshot:
    now = datetime.now(UTC)
    base: dict[str, Any] = {"login": "miusuario", "last_success": now - timedelta(seconds=12)}
    base.update(kw)
    state = State(prs={p.id: Tracked(p) for p in prs}, baseline=True)
    return Snapshot(health=health, state=state, **base)


def scenarios() -> dict[str, Any]:
    gh = GitHubProvider(transport=None)
    cfg = Config(max_per_block=5)
    cfg.github.org = "contoso"
    now = datetime.now(UTC)

    def panel(snap: Snapshot, unseen: set[str] | None = None, c: Config = cfg) -> Any:
        return view.panel(
            snap,
            provider=gh,
            cfg=c,
            unseen=unseen or set(),
            pinned=False,
            now=now,
            version=__version__,
        )

    unconfigured = Config()
    many = [_pr(100 + i, f"Propio número {i}") for i in range(8)] + [
        _pr(
            200 + i,
            f"Revisión número {i}",
            relation=Relation.REVIEWER,
            review_pending=True,
            author="colega",
        )
        for i in range(7)
    ]
    out: dict[str, Any] = {
        "normal": {"panel": panel(_snap(_mine() + _review()))},
        "sin-configurar": {
            "panel": panel(
                _snap([], Health.UNCONFIGURED, login=None, last_success=None), c=unconfigured
            )
        },
        "vacio": {"panel": panel(_snap([]))},
        "por-encima-del-tope": {"panel": panel(_snap(many))},
        "todos-los-estados": {
            "panel": panel(_snap(_all_states()), c=Config(max_per_block=20, github=cfg.github))
        },
        "novedades": {"panel": panel(_snap(_mine() + _review()), unseen={"PR_142", "PR_150"})},
        "desactualizado": {
            "panel": panel(
                _snap(_mine() + _review(), Health.STALE, last_success=now - timedelta(minutes=7))
            )
        },
        "limite-agotado": {
            "panel": panel(
                _snap(_mine(), Health.RATE_LIMITED, suspended_until=now + timedelta(minutes=12))
            )
        },
        "token-rechazado": {"panel": panel(_snap(_mine(), Health.INVALID_CREDENTIAL))},
    }
    for p in out.values():
        p["panel"]["pinned"] = False
    out["fijado"] = {"panel": dict(out["normal"]["panel"], pinned=True)}

    def opts(*values: str) -> list[dict[str, str]]:
        return [{"value": v, "label": gh.scope_label(v)} for v in values]

    orgs = {
        "ok": True,
        "login": "miusuario",
        "scopes": opts("user:miusuario", "Acme", "beta-labs", "contoso"),
    }
    out["ajustes-primera-vez"] = {
        "settings": settings_model.load(
            unconfigured, gh, has_token=False, plaintext=False, first_run=True
        ),
        "replies": {
            "settings_verify_token": orgs,
            "settings_verify": {"ok": True, "login": "miusuario"},
        },
    }
    out["ajustes-con-token"] = {
        "settings": settings_model.load(cfg, gh, has_token=True, plaintext=False, first_run=False),
        "replies": {
            "settings_verify_token": orgs,
            "settings_verify": {"ok": True, "login": "miusuario"},
        },
    }
    out["ajustes-sin-organizaciones"] = {
        "settings": settings_model.load(
            unconfigured, gh, has_token=False, plaintext=False, first_run=True
        ),
        "replies": {
            "settings_verify_token": {
                "ok": True,
                "login": "miusuario",
                "scopes": opts("user:miusuario"),
            },
            "settings_verify": {
                "ok": False,
                "kind": "scope",
                "message": "el token no ve ningún repositorio de la organización",
            },
        },
    }
    out["ajustes-token-rechazado"] = {
        "settings": settings_model.load(cfg, gh, has_token=True, plaintext=True, first_run=False),
        "replies": {"settings_verify_token": {"ok": False, "kind": "invalid", "message": "401"}},
    }

    # Ajustes con la otra forja: la nube, una instancia propia y los dos
    # fallos que solo existen con host configurable.
    nube = GitLabProvider("https://gitlab.com")
    propia = GitLabProvider("https://gitlab.empresa.com")
    cfg_nube = Config(provider="gitlab")
    cfg_propia = Config(provider="gitlab")
    cfg_propia.gitlab.host = propia.host
    cfg_propia.gitlab.group = "empresa/plataforma"
    grupos = {
        "ok": True,
        "login": "miusuario",
        "scopes": [
            {"value": v, "label": propia.scope_label(v)}
            for v in ("user:miusuario", "empresa", "empresa/plataforma", "empresa/plataforma/red")
        ],
    }
    out["ajustes-gitlab-nube"] = {
        "settings": settings_model.load(
            cfg_nube, nube, has_token=False, plaintext=False, first_run=True
        ),
        "replies": {
            "settings_verify_token": grupos,
            "settings_verify": {"ok": True, "login": "miusuario"},
        },
    }
    out["ajustes-gitlab-propia"] = {
        "settings": settings_model.load(
            cfg_propia, propia, has_token=True, plaintext=False, first_run=False
        ),
        "replies": {
            "settings_verify_token": grupos,
            "settings_verify": {"ok": True, "login": "miusuario"},
        },
    }
    out["ajustes-gitlab-inalcanzable"] = {
        "settings": settings_model.load(
            cfg_propia, propia, has_token=False, plaintext=False, first_run=True
        ),
        "replies": {
            "settings_verify_token": {
                "ok": False,
                "kind": "network",
                "message": "gitlab.empresa.com no responde como una instancia de GitLab",
            },
        },
    }
    out["ajustes-gitlab-version-vieja"] = {
        "settings": settings_model.load(
            cfg_propia, propia, has_token=False, plaintext=False, first_run=True
        ),
        "replies": {
            "settings_verify_token": {
                "ok": False,
                "kind": "scope",
                "message": "esta instancia es GitLab 15.11.3 y hace falta 16.0 o posterior",
            },
        },
    }
    return out


def write_scenarios() -> Path:
    SCENARIOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCENARIOS_FILE.write_text(json.dumps(scenarios(), ensure_ascii=False, indent=1), "utf-8")
    return SCENARIOS_FILE


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> int:
    write_scenarios()
    handler = functools.partial(_Quiet, directory=str(UI_DIR))
    port = 0
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/preview/index.html"
    print(f"Vista previa en {url}  (Ctrl+C para salir)", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
