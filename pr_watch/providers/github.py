"""Proveedor de GitHub (github.com) por GraphQL, de solo lectura.

GraphQL se consulta por POST, asi que "solo lectura" no puede ser "solo GET".
La garantia es doble: el token no tiene permisos de escritura y `_send` se
niega a enviar cualquier documento que contenga una `mutation` o una
`subscription`. Las consultas son constantes del modulo; la organizacion viaja
como variable, nunca concatenada.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import quote

from pr_watch.credential import Token
from pr_watch.providers.base import (
    INACCESSIBLE,
    ChecksState,
    Descriptor,
    FetchResult,
    Identity,
    Inaccessible,
    InvalidCredential,
    NetworkError,
    ProviderError,
    PrState,
    PullRequest,
    RateLimited,
    Relation,
    ScopeInaccessible,
    ScopeList,
    Vocabulary,
)
from pr_watch.providers.http import Response, Transport, assert_read_only, requests_transport

API_URL = "https://api.github.com/graphql"
REPOS_URL = "https://api.github.com/user/repos"
WEB_URL = "https://github.com"
TIMEOUT_SECS = 15
REPO_PAGES = 5  # hasta 500 repositorios para deducir organizaciones
PAGE_SIZE = 50
CREATE_TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"

# Permisos de solo lectura que se le indican al usuario en Ajustes.
TOKEN_PERMISSIONS = ("Pull requests", "Metadata", "Commit statuses", "Checks")

_ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

_PR_FIELDS = """
fragment PR on PullRequest {
  id number title url isDraft state updatedAt
  repository { nameWithOwner }
  author { login }
  mergeable reviewDecision
  latestOpinionatedReviews(first: 50) { nodes { state author { login } } }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  reviewThreads(first: 100) { nodes { isResolved } }
}
fragment Page on SearchResultItemConnection {
  issueCount
  pageInfo { hasNextPage endCursor }
  nodes { ...PR }
}
"""

WATCH_QUERY = (
    """
query Watch(
  $qa: String!, $qr: String!, $qs: String!,
  $ca: String, $cr: String, $cs: String,
  $ia: Boolean!, $ir: Boolean!, $is: Boolean!
) {
  author: search(type: ISSUE, query: $qa, first: __N__, after: $ca) @include(if: $ia) { ...Page }
  reviewer: search(type: ISSUE, query: $qr, first: __N__, after: $cr) @include(if: $ir) { ...Page }
  assignee: search(type: ISSUE, query: $qs, first: __N__, after: $cs) @include(if: $is) { ...Page }
}
"""
    + _PR_FIELDS
).replace("__N__", str(PAGE_SIZE))

PERSONAL_PREFIX = "user:"

PERSONAL_VERIFY_QUERY = """
query VerifyPersonal {
  viewer { login repositories(first: 1, ownerAffiliations: [OWNER]) { totalCount } }
}
"""

VERIFY_QUERY = """
query Verify($org: String!) {
  viewer { login }
  organization(login: $org) { login repositories(first: 1) { totalCount } }
}
"""

SCOPES_QUERY = """
query Scopes($after: String) {
  viewer {
    login
    organizations(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { login }
    }
  }
}
"""

STATES_QUERY = """
query States($ids: [ID!]!) {
  nodes(ids: $ids) { ... on PullRequest { id state } }
}
"""

# Alias de la consulta -> (relacion, calificador de busqueda, variable de query,
# variable de cursor, variable de inclusion).
_RELATIONS: dict[str, tuple[Relation, str, str, str, str]] = {
    "author": (Relation.AUTHOR, "author:@me", "qa", "ca", "ia"),
    "reviewer": (Relation.REVIEWER, "review-requested:@me", "qr", "cr", "ir"),
    "assignee": (Relation.ASSIGNEE, "assignee:@me", "qs", "cs", "is"),
}


def _headers(token: Token) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token.reveal()}",
        "Accept": "application/vnd.github+json",
    }


def valid_org(org: str) -> bool:
    return bool(_ORG_RE.match(org))


def parse_scope(scope: str) -> tuple[str, str]:
    """('user', login) para la cuenta personal, ('org', nombre) para una organizacion.

    El nombre se valida aqui porque acaba dentro de una busqueda: nada de
    espacios ni calificadores colados.
    """
    scope = scope.strip()
    kind, name = "org", scope
    if scope.startswith(PERSONAL_PREFIX):
        kind, name = "user", scope.removeprefix(PERSONAL_PREFIX)
    if not valid_org(name):
        raise ScopeInaccessible("el nombre de la cuenta u organizacion no es valido")
    return kind, name


def search_query(scope: str, qualifier: str) -> str:
    kind, name = parse_scope(scope)
    return f"{kind}:{name} is:pr is:open archived:false {qualifier}"


@dataclass(slots=True)
class _Page:
    nodes: list[dict[str, Any]]
    has_next: bool
    cursor: str | None


class GitHubProvider:
    name = "github"
    DISPLAY_NAME = "GitHub"
    vocabulary = Vocabulary(noun="PR", ref_prefix="#", host_label="github.com")

    @property
    def instance_key(self) -> str:
        # GitHub solo vive en github.com: la clave es la de siempre, para que
        # el token y el estado ya guardados sigan donde estan.
        return self.name

    @property
    def descriptor(self) -> Descriptor:
        return Descriptor(
            display_name=self.DISPLAY_NAME,
            scope_label="Cuenta u organización",
            scope_placeholder="Nombre de la organización",
            token_permissions=TOKEN_PERMISSIONS,
            create_token_url=CREATE_TOKEN_URL,
            configurable_host=False,
        )

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport
        # Ultimo valor conocido de conflicto por PR, para no oscilar cuando
        # GitHub todavia esta calculando la fusionabilidad (UNKNOWN).
        self.known_conflicts: dict[str, bool] = {}

    @property
    def transport(self) -> Transport:
        if self._transport is None:
            self._transport = requests_transport()
        return self._transport

    # ---- envio ----

    def _send(self, document: str, variables: dict[str, Any], token: Token) -> dict[str, Any]:
        assert_read_only(document)
        resp = self.transport(
            API_URL, {"query": document, "variables": variables}, _headers(token), TIMEOUT_SECS
        )
        body = self._check(resp)
        if not isinstance(body, dict):
            raise NetworkError("respuesta no es un objeto JSON")
        body = cast(dict[str, Any], body)
        for err in _errors(body):
            if err.get("type") == "RATE_LIMITED":
                raise _rate_limit(resp.headers, force=True) or RateLimited(
                    datetime.now(UTC) + timedelta(minutes=1)
                )
        return body

    def _get(self, url: str, token: Token) -> Any:
        """Una peticion REST de lectura. Solo GET: no hay cuerpo que enviar."""
        return self._check(self.transport(url, None, _headers(token), TIMEOUT_SECS))

    def _check(self, resp: Response) -> Any:
        status = resp.status_code
        if status == 401:
            raise InvalidCredential("GitHub rechazo el token")
        if status in (403, 429):
            limited = _rate_limit(resp.headers)
            if limited is not None:
                raise limited
            raise InvalidCredential(f"GitHub nego el acceso ({status})")
        if status >= 500:
            raise NetworkError(f"GitHub respondio {status}")
        if status != 200:
            raise NetworkError(f"respuesta inesperada {status}")
        try:
            return resp.json()
        except ValueError:
            raise NetworkError("respuesta no es JSON") from None

    # ---- verificacion ----

    def list_scopes(self, token: Token) -> ScopeList:
        """El token por si solo: login y organizaciones visibles.

        Primero las organizaciones del usuario (un token clasico con
        `read:org` las ve). Si no hay ninguna, se deducen de los repositorios
        accesibles. Una lista vacia al final no es un error.
        """
        orgs: list[str] = []
        after: str | None = None
        login = ""
        for _ in range(20):  # 2000 organizaciones: de sobra
            body = self._send(SCOPES_QUERY, {"after": after}, token)
            viewer = (body.get("data") or {}).get("viewer") or {}
            login = str(viewer.get("login") or "")
            if not login:
                raise InvalidCredential("GitHub no devolvio el usuario")
            conn = viewer.get("organizations") or {}
            orgs.extend(str(n["login"]) for n in (conn.get("nodes") or []) if n and n.get("login"))
            info = conn.get("pageInfo") or {}
            after = info.get("endCursor")
            if not info.get("hasNextPage") or not after:
                break
        if not orgs:
            # Un fine-grained token recibe siempre una lista vacia de
            # organizaciones. Pero ve los repositorios a los que tiene acceso, y
            # el dueno de cada uno: las organizaciones salen de ahi.
            orgs = self._orgs_from_repos(token)
        # La cuenta personal va siempre, primero.
        return ScopeList(
            identity=Identity(login=login),
            scopes=(PERSONAL_PREFIX + login, *sorted(set(orgs), key=str.lower)),
        )

    def _orgs_from_repos(self, token: Token) -> list[str]:
        orgs: set[str] = set()
        for page in range(1, REPO_PAGES + 1):
            repos = self._get(f"{REPOS_URL}?per_page=100&page={page}", token)
            if not isinstance(repos, list):
                break
            items = cast(list[Any], repos)
            for repo in items:
                owner = repo.get("owner") if isinstance(repo, dict) else None
                if isinstance(owner, dict) and owner.get("type") == "Organization":
                    login = owner.get("login")
                    if isinstance(login, str) and login:
                        orgs.add(login)
            if len(items) < 100:
                break
        return list(orgs)

    def verify(self, scope: str, token: Token) -> Identity:
        kind, org = parse_scope(scope)
        if kind == "user":
            return self._verify_personal(org, token)
        body = self._send(VERIFY_QUERY, {"org": org}, token)
        data = body.get("data") or {}
        viewer = data.get("viewer") or {}
        login = viewer.get("login")
        if not login:
            raise InvalidCredential("GitHub no devolvio el usuario")
        organization = data.get("organization")
        if not organization:
            raise ScopeInaccessible(f"la organizacion {org} no existe o el token no tiene acceso")
        total = ((organization.get("repositories") or {}).get("totalCount")) or 0
        if total == 0:
            raise ScopeInaccessible(
                f"el token no ve ningun repositorio de {org}: revisa el dueno del token "
                "o si la organizacion aun no lo aprobo"
            )
        return Identity(login=str(login))

    def _verify_personal(self, login: str, token: Token) -> Identity:
        body = self._send(PERSONAL_VERIFY_QUERY, {}, token)
        viewer = (body.get("data") or {}).get("viewer") or {}
        me = viewer.get("login")
        if not me:
            raise InvalidCredential("GitHub no devolvio el usuario")
        if str(me).lower() != login.lower():
            raise ScopeInaccessible(f"la cuenta personal del token es {me}, no {login}")
        total = ((viewer.get("repositories") or {}).get("totalCount")) or 0
        if total == 0:
            raise ScopeInaccessible(
                "el token no ve ningun repositorio personal: revisa que el dueno del "
                "token sea tu cuenta y que tenga acceso a tus repositorios"
            )
        return Identity(login=str(me))

    # ---- listado ----

    def fetch_open(self, scope: str, token: Token) -> FetchResult:
        parse_scope(scope)  # valida antes de tocar la red

        nodes: dict[str, list[dict[str, Any]]] = {alias: [] for alias in _RELATIONS}
        cursors: dict[str, str | None] = {alias: None for alias in _RELATIONS}
        pending = set(_RELATIONS)
        failed: dict[str, str] = {}

        while pending:
            variables: dict[str, Any] = {}
            for alias, (_, qualifier, qv, cv, iv) in _RELATIONS.items():
                variables[qv] = search_query(scope, qualifier)
                variables[cv] = cursors[alias]
                variables[iv] = alias in pending
            body = self._send(WATCH_QUERY, variables, token)
            data = body.get("data") or {}
            errors_by_alias = _errors_by_alias(body)
            if not data and errors_by_alias.get("") and not failed:
                raise NetworkError(errors_by_alias[""])
            for alias in list(pending):
                page = _page(data.get(alias))
                if page is None:
                    failed[alias] = errors_by_alias.get(alias) or errors_by_alias.get("") or "?"
                    pending.discard(alias)
                    continue
                nodes[alias].extend(page.nodes)
                if page.has_next and page.cursor:
                    cursors[alias] = page.cursor
                else:
                    pending.discard(alias)

        if len(failed) == len(_RELATIONS):
            raise NetworkError("fallaron las tres consultas: " + "; ".join(failed.values()))

        by_id: dict[str, tuple[Relation, dict[str, Any]]] = {}
        review_requested: set[str] = set()
        for alias, (relation, *_rest) in _RELATIONS.items():
            for node in nodes[alias]:
                pr_id = node.get("id")
                if not isinstance(pr_id, str):
                    continue
                if relation is Relation.REVIEWER:
                    review_requested.add(pr_id)
                current = by_id.get(pr_id)
                if current is None or relation < current[0]:
                    by_id[pr_id] = (relation, node)

        prs = [
            self.translate(node, relation, review_pending=pr_id in review_requested)
            for pr_id, (relation, node) in by_id.items()
        ]
        return FetchResult(
            prs=prs,
            complete=not failed,
            errors=[f"{a}: {m}" for a, m in failed.items()],
        )

    def translate(
        self, node: dict[str, Any], relation: Relation, *, review_pending: bool
    ) -> PullRequest:
        pr_id = str(node["id"])
        reviews = ((node.get("latestOpinionatedReviews") or {}).get("nodes")) or []
        approvals: list[str] = []
        changes_requested = False
        for review in reviews:
            state = review.get("state")
            login = ((review.get("author") or {}).get("login")) or "?"
            if state == "APPROVED":
                approvals.append(login)
            elif state == "CHANGES_REQUESTED":
                changes_requested = True

        commits = ((node.get("commits") or {}).get("nodes")) or []
        rollup = None
        if commits:
            rollup = (((commits[-1] or {}).get("commit") or {}).get("statusCheckRollup")) or None
        checks = _checks((rollup or {}).get("state"))

        mergeable = node.get("mergeable")
        conflicts: bool | None
        if mergeable == "CONFLICTING":
            conflicts = True
        elif mergeable == "MERGEABLE":
            conflicts = False
        else:
            conflicts = self.known_conflicts.get(pr_id)
        if conflicts is not None:
            self.known_conflicts[pr_id] = conflicts

        threads = ((node.get("reviewThreads") or {}).get("nodes")) or []
        unresolved = sum(1 for t in threads if t and not t.get("isResolved"))

        draft = bool(node.get("isDraft"))
        decision = node.get("reviewDecision")
        approved = decision == "APPROVED" or (decision is None and len(approvals) > 0)
        ready = (
            not draft
            and conflicts is False
            and checks in (ChecksState.SUCCESS, ChecksState.NONE)
            and not changes_requested
            and approved
        )

        return PullRequest(
            id=pr_id,
            repo=str(((node.get("repository") or {}).get("nameWithOwner")) or "?"),
            number=int(node.get("number") or 0),
            title=str(node.get("title") or ""),
            url=str(node.get("url") or ""),
            author=str(((node.get("author") or {}).get("login")) or "ghost"),
            state=_state(node.get("state")),
            draft=draft,
            relation=relation,
            approvals=tuple(sorted(approvals, key=str.lower)),
            changes_requested=changes_requested,
            checks=checks,
            conflicts=conflicts,
            unresolved=unresolved,
            ready_to_merge=ready,
            review_pending=review_pending,
            updated_at=_parse_time(node.get("updatedAt")),
        )

    # ---- estado de los que desaparecen ----

    def fetch_states(self, ids: list[str], token: Token) -> dict[str, PrState | Inaccessible]:
        result: dict[str, PrState | Inaccessible] = {}
        for start in range(0, len(ids), 100):
            batch = ids[start : start + 100]
            body = self._send(STATES_QUERY, {"ids": batch}, token)
            found = ((body.get("data") or {}).get("nodes")) or []
            seen: dict[str, PrState] = {}
            for node in found:
                if node and isinstance(node.get("id"), str):
                    seen[node["id"]] = _state(node.get("state"))
            for pr_id in batch:
                result[pr_id] = seen.get(pr_id, INACCESSIBLE)
        return result

    # ---- URL ----

    def block_url(self, scope: str, relations: tuple[Relation, ...]) -> str:
        qualifier = "author:@me" if Relation.AUTHOR in relations else "review-requested:@me"
        return f"{WEB_URL}/pulls?q=" + quote(search_query(scope, qualifier))

    def scope_label(self, scope: str) -> str:
        if scope.startswith(PERSONAL_PREFIX):
            # El login ya sale en la fila Usuario: no se repite.
            return "Cuenta personal"
        return scope

    def pr_ref(self, pr: PullRequest) -> str:
        return f"{self.vocabulary.ref_prefix}{pr.number}"

    def allows_url(self, url: str) -> bool:
        return url.startswith(WEB_URL + "/")


# ---- ayudas ----


def _errors(body: dict[str, Any]) -> list[dict[str, Any]]:
    errs = body.get("errors")
    if not isinstance(errs, list):
        return []
    return [cast(dict[str, Any], e) for e in cast(list[Any], errs) if isinstance(e, dict)]


def _errors_by_alias(body: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in _errors(body):
        path = err.get("path")
        alias = str(path[0]) if isinstance(path, list) and path else ""
        out.setdefault(alias, str(err.get("type") or err.get("message") or "error"))
    return out


def _page(raw: Any) -> _Page | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    info = raw.get("pageInfo") or {}
    nodes = [n for n in (raw.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    return _Page(nodes=nodes, has_next=bool(info.get("hasNextPage")), cursor=info.get("endCursor"))


def _rate_limit(headers: Mapping[str, str], *, force: bool = False) -> RateLimited | None:
    h = {k.lower(): v for k, v in headers.items()}
    now = datetime.now(UTC)
    retry_after = h.get("retry-after")
    if retry_after and retry_after.isdigit():
        return RateLimited(now + timedelta(seconds=int(retry_after)))
    if force or h.get("x-ratelimit-remaining") == "0":
        reset = h.get("x-ratelimit-reset")
        if reset and reset.isdigit():
            return RateLimited(datetime.fromtimestamp(int(reset), UTC))
        return RateLimited(now + timedelta(minutes=1))
    return None


def _checks(state: Any) -> ChecksState:
    match state:
        case "SUCCESS":
            return ChecksState.SUCCESS
        case "FAILURE" | "ERROR":
            return ChecksState.FAILURE
        case "PENDING" | "EXPECTED":
            return ChecksState.PENDING
        case _:
            return ChecksState.NONE


def _state(raw: Any) -> PrState:
    match raw:
        case "MERGED":
            return PrState.MERGED
        case "CLOSED":
            return PrState.CLOSED
        case _:
            return PrState.OPEN


def _parse_time(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, UTC)


def _check_main() -> int:
    """Diagnostico: `python -m pr_watch.providers.github --check`.

    Verifica la credencial guardada contra la organizacion configurada e
    imprime un resumen de lo que llega, sin mostrar el token.
    """
    from pr_watch import config as config_mod
    from pr_watch.credential import CredentialStore, system_keyring

    cfg = config_mod.load(config_mod.config_dir() / config_mod.CONFIG_FILE).config
    store = CredentialStore("github", config_mod.config_dir(), keyring_backend=system_keyring())
    loaded = store.load()
    if loaded is None:
        print("No hay token: define PR_WATCH_TOKEN o configuralo en la aplicacion.")
        return 2
    org = cfg.github.org
    print(f"Organizacion: {org or '(sin configurar)'} · token desde {loaded.source.value}")
    gh = GitHubProvider()
    try:
        ident = gh.verify(org, loaded.token)
        print(f"Conectado como {ident.login}")
        result = gh.fetch_open(org, loaded.token)
    except ProviderError as e:
        print(f"Error ({type(e).__name__}): {e}")
        return 1
    print(f"Completo: {result.complete} {result.errors}")
    for pr in sorted(result.prs, key=lambda p: (p.relation, p.repo, p.number)):
        print(
            f"  [{pr.relation.name:8}] {pr.repo}#{pr.number} draft={pr.draft} "
            f"aprob={list(pr.approvals)} cambios={pr.changes_requested} checks={pr.checks} "
            f"conflictos={pr.conflicts} sin_resolver={pr.unresolved} lista={pr.ready_to_merge}"
        )
    sin_checks = sum(1 for p in result.prs if p.checks is ChecksState.NONE)
    print(f"PR sin estado de checks: {sin_checks} de {len(result.prs)}")
    return 0


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        sys.exit(_check_main())
    print("Uso: python -m pr_watch.providers.github --check")
