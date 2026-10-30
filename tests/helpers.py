from datetime import UTC, datetime
from typing import Any

from pr_watch.providers.base import ChecksState, PrState, PullRequest, Relation


def make_pr(number: int = 1, **kw: Any) -> PullRequest:
    base: dict[str, Any] = {
        "id": f"PR_{number}",
        "repo": "contoso/netops",
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/contoso/netops/pull/{number}",
        "author": "miusuario",
        "state": PrState.OPEN,
        "draft": False,
        "relation": Relation.AUTHOR,
        "approvals": (),
        "changes_requested": False,
        "checks": ChecksState.NONE,
        "conflicts": False,
        "unresolved": 0,
        "ready_to_merge": False,
        "review_pending": False,
        "updated_at": datetime(2026, 10, 29, 10, 0, tzinfo=UTC),
    }
    base.update(kw)
    return PullRequest(**base)
