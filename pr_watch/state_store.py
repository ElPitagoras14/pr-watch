"""Estado persistido entre arranques, un archivo por proveedor.

Escritura atomica (temporal + `os.replace`): una interrupcion a mitad deja el
archivo anterior intacto. Un archivo ilegible o de otra version se descarta y
se arranca como la primera vez.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pr_watch.polling import State, Tracked
from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation

SCHEMA_VERSION = 1

_log = logging.getLogger(__name__)


def path_for(config_dir: Path, provider: str) -> Path:
    return config_dir / f"state-{provider}.json"


def _pr_to_json(pr: PullRequest) -> dict[str, Any]:
    return {
        "id": pr.id,
        "repo": pr.repo,
        "number": pr.number,
        "title": pr.title,
        "url": pr.url,
        "author": pr.author,
        "state": pr.state.value,
        "draft": pr.draft,
        "relation": pr.relation.name,
        "approvals": list(pr.approvals),
        "changes_requested": pr.changes_requested,
        "checks": pr.checks.value,
        "conflicts": pr.conflicts,
        "unresolved": pr.unresolved,
        "ready_to_merge": pr.ready_to_merge,
        "review_pending": pr.review_pending,
        "updated_at": pr.updated_at.isoformat(),
    }


def _pr_from_json(d: dict[str, Any]) -> PullRequest:
    conflicts = d["conflicts"]
    if conflicts is not None and not isinstance(conflicts, bool):
        raise ValueError("conflicts")
    return PullRequest(
        id=str(d["id"]),
        repo=str(d["repo"]),
        number=int(d["number"]),
        title=str(d["title"]),
        url=str(d["url"]),
        author=str(d["author"]),
        state=PrState(d["state"]),
        draft=bool(d["draft"]),
        relation=Relation[d["relation"]],
        approvals=tuple(str(a) for a in d["approvals"]),
        changes_requested=bool(d["changes_requested"]),
        checks=ChecksState(d["checks"]),
        conflicts=conflicts,
        unresolved=int(d["unresolved"]),
        ready_to_merge=bool(d["ready_to_merge"]),
        review_pending=bool(d["review_pending"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


def to_json(state: State) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "baseline": state.baseline,
        "prs": [
            {
                "pr": _pr_to_json(t.pr),
                "terminal_since": t.terminal_since.isoformat() if t.terminal_since else None,
                "notified": sorted(t.notified),
            }
            for t in state.prs.values()
        ],
    }


def from_json(data: Any) -> State:
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        raise ValueError("version de esquema distinta")
    prs: dict[str, Tracked] = {}
    for item in data["prs"]:
        pr = _pr_from_json(item["pr"])
        since = item.get("terminal_since")
        prs[pr.id] = Tracked(
            pr=pr,
            terminal_since=datetime.fromisoformat(since) if since else None,
            notified=frozenset(str(n) for n in item.get("notified", [])),
        )
    return State(prs=prs, baseline=bool(data.get("baseline")))


def load(path: Path) -> State:
    try:
        raw = path.read_text("utf-8")
    except FileNotFoundError:
        return State()
    except OSError as e:
        _log.warning("No se pudo leer el estado %s: %s", path, e)
        return State()
    try:
        return from_json(json.loads(raw))
    except (ValueError, KeyError, TypeError) as e:
        _log.warning("Estado %s descartado: %s", path, e)
        return State()


def save(state: State, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(to_json(state), ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, path)
