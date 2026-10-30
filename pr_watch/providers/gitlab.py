"""Proveedor de GitLab (nube y self-hosted) por GraphQL, de solo lectura.

La nube y una instancia propia son el mismo codigo: lo unico que cambia es el
host, que llega en el constructor. De el salen la URL de la API, la web, el
enlace para crear el token y las URL que la aplicacion acepta abrir.

Como en GitHub, "solo lectura" no puede ser "solo GET" porque GraphQL se
consulta por POST: la garantia es el ambito `read_api` del token mas el
rechazo de cualquier documento con `mutation` o `subscription`.

Dos cosas se aprendieron contra una instancia real (CE 19.2) y condicionan
este modulo:

- La introspeccion del esquema devuelve un esquema cacheado que anuncia campos
  que la instancia luego rechaza. Aqui solo se piden campos comprobados
  ejecutando consultas, y todos existen en la edicion Community.
- El limite que aprieta no es la paginacion (100 nodos) sino la complejidad
  (250 por peticion). El documento de sondeo marca 169 con pagina de 50; cada
  campo nuevo lo acerca al techo, y por eso se pide `queryComplexity`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import quote, urlsplit

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

TIMEOUT_SECS = 15
PAGE_SIZE = 50  # 169 de 250 de complejidad con los campos de abajo
STATES_BATCH = 50
GROUP_PAGES = 10  # hasta 1000 grupos
MIN_VERSION = (16, 0)
# Por encima de esta fraccion del limite de complejidad se deja aviso.
COMPLEXITY_WARN = 0.8

TOKEN_PERMISSIONS = ("read_api",)

PERSONAL_PREFIX = "user:"

# Rutas de grupo: segmentos separados por `/`, como `empresa/plataforma/red`.
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$")

_log = logging.getLogger(__name__)

# Campos comprobados contra GitLab CE 19.2.7. Fuera quedan los de pago
# (`approvalsRequired`, `approvalsLeft`, `changeRequesters`), que una instancia
# Community rechaza y que el modelo neutro no necesita.
_MR_FIELDS = """
fragment MR on MergeRequest {
  id iid title webUrl state draft updatedAt conflicts mergeStatusEnum approved
  resolvableDiscussionsCount resolvedDiscussionsCount
  project { fullPath }
  author { username }
  approvedBy { nodes { username } }
  reviewers { nodes { username mergeRequestInteraction { reviewState } } }
  headPipeline { status }
}
fragment Pag on MergeRequestConnection {
  pageInfo { hasNextPage endCursor }
  nodes { ...MR }
}
"""

WATCH_QUERY = (
    """
query Watch(
  $gid: GroupID, $n: Int!,
  $ca: String, $cs: String, $cr: String,
  $ia: Boolean!, $is: Boolean!, $ir: Boolean!
) {
  queryComplexity { score limit }
  currentUser {
    username
    autor: authoredMergeRequests(state: opened, groupId: $gid, first: $n, after: $ca)
      @include(if: $ia) { ...Pag }
    asignado: assignedMergeRequests(state: opened, groupId: $gid, first: $n, after: $cs)
      @include(if: $is) { ...Pag }
    revisor: reviewRequestedMergeRequests(state: opened, groupId: $gid, first: $n, after: $cr)
      @include(if: $ir) { ...Pag }
  }
}
"""
    + _MR_FIELDS
)

METADATA_QUERY = """
query Meta { metadata { version enterprise } currentUser { username } }
"""

SCOPES_QUERY = """
query Scopes($after: String) {
  currentUser {
    username
    groups(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { id fullPath }
    }
  }
}
"""

GROUP_QUERY = """
query Grupo($ruta: ID!) { currentUser { username } group(fullPath: $ruta) { id fullPath } }
"""

# Alias de la consulta -> (relacion, variable de cursor, variable de inclusion).
_RELATIONS: dict[str, tuple[Relation, str, str]] = {
    "autor": (Relation.AUTHOR, "ca", "ia"),
    "revisor": (Relation.REVIEWER, "cr", "ir"),
    "asignado": (Relation.ASSIGNEE, "cs", "is"),
}

# La revision del usuario sigue pendiente mientras este en uno de estos estados.
_PENDING_REVIEW = ("UNREVIEWED", "REVIEW_STARTED")


def slug_for_host(host: str) -> str:
    """Identificador de la instancia valido como nombre de archivo y de entrada.

    `https://gitlab.empresa.com:8443/git` -> `gitlab-empresa-com-8443-git`.
    """
    sin_esquema = host.split("://", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "-", sin_esquema.lower()).strip("-")


def parse_scope(scope: str) -> tuple[str, str]:
    """('user', login) para el espacio personal, ('group', ruta) para un grupo."""
    scope = scope.strip().strip("/")
    kind, name = "group", scope
    if scope.startswith(PERSONAL_PREFIX):
        kind, name = "user", scope.removeprefix(PERSONAL_PREFIX).strip("/")
    if not name or not _PATH_RE.match(name):
        raise ScopeInaccessible("el grupo o espacio personal no es una ruta valida")
    if kind == "user" and "/" in name:
        raise ScopeInaccessible("un espacio personal no lleva subgrupos")
    return kind, name


@dataclass(slots=True)
class _Page:
    nodes: list[dict[str, Any]]
    has_next: bool
    cursor: str | None


class GitLabProvider:
    name = "gitlab"
    DISPLAY_NAME = "GitLab"

    def __init__(self, host: str, transport: Transport | None = None) -> None:
        self.host = host.rstrip("/")
        self.api_url = f"{self.host}/api/graphql"
        self.vocabulary = Vocabulary(
            noun="MR", ref_prefix="!", host_label=urlsplit(self.host).netloc or self.host
        )
        self._transport = transport
        # Ultimo valor conocido de conflicto por MR: GitLab calcula la
        # fusionabilidad de forma asincrona y oscilaria entre ciclos.
        self.known_conflicts: dict[str, bool] = {}
        # Ruta de grupo -> identificador global, para no resolverlo cada vez.
        self._group_ids: dict[str, str] = {}
        self._version = ""
        self._login = ""

    @property
    def instance_key(self) -> str:
        return f"{self.name}@{slug_for_host(self.host)}"

    @property
    def descriptor(self) -> Descriptor:
        return Descriptor(
            display_name=self.DISPLAY_NAME,
            scope_label="Grupo o espacio personal",
            scope_placeholder="Ruta del grupo (empresa/plataforma)",
            token_permissions=TOKEN_PERMISSIONS,
            create_token_url=f"{self.host}/-/user_settings/personal_access_tokens",
            configurable_host=True,
        )

    @property
    def transport(self) -> Transport:
        if self._transport is None:
            self._transport = requests_transport()
        return self._transport

    # ---- envio ----

    def _headers(self, token: Token) -> dict[str, str]:
        return {"Authorization": f"Bearer {token.reveal()}", "Accept": "application/json"}

    def _send(self, document: str, variables: dict[str, Any], token: Token) -> dict[str, Any]:
        assert_read_only(document)
        resp = self.transport(
            self.api_url,
            {"query": document, "variables": variables},
            self._headers(token),
            TIMEOUT_SECS,
        )
        body = self._check(resp)
        if not isinstance(body, dict):
            raise NetworkError("la respuesta no es un objeto JSON")
        body = cast(dict[str, Any], body)
        self._raise_for_errors(body)
        return body

    def _check(self, resp: Response) -> Any:
        status = resp.status_code
        if status == 401:
            raise InvalidCredential("GitLab rechazo el token")
        if status == 403:
            raise InvalidCredential("GitLab nego el acceso: revisa el ambito del token")
        if status == 429:
            raise _rate_limit(resp.headers)
        if status == 404:
            raise NetworkError(
                f"{self.host} no responde como una instancia de GitLab: revisa la direccion"
            )
        if status >= 500:
            raise NetworkError(f"GitLab respondio {status}")
        if status != 200:
            raise NetworkError(f"respuesta inesperada {status}")
        try:
            return resp.json()
        except ValueError:
            raise NetworkError("la respuesta no es JSON") from None

    def _raise_for_errors(self, body: dict[str, Any]) -> None:
        """Traduce los errores de GraphQL que no son fallos de datos puntuales.

        Un campo que la instancia no conoce no es un error de red cualquiera:
        el mensaje dice cual es y que version hay, que es lo que hace falta
        para arreglarlo.
        """
        for err in _errors(body):
            ext = err.get("extensions") or {}
            codigo = ext.get("code")
            mensaje = str(err.get("message") or "error")
            if codigo == "undefinedField":
                campo = f"{ext.get('typeName')}.{ext.get('fieldName')}"
                version = self._version or "desconocida"
                raise NetworkError(f"tu instancia de GitLab (version {version}) no expone {campo}")
            if "complexity" in mensaje.lower():
                raise NetworkError(f"GitLab rechazo la consulta por compleja: {mensaje}")

    # ---- version y edicion ----

    def _check_instance(self, token: Token) -> str:
        """Comprueba version y edicion. Devuelve el login del token."""
        body = self._send(METADATA_QUERY, {}, token)
        data = body.get("data") or {}
        login = str(((data.get("currentUser") or {}).get("username")) or "")
        if not login:
            raise InvalidCredential("GitLab no devolvio el usuario del token")
        self._login = login

        meta = data.get("metadata") or {}
        version = str(meta.get("version") or "")
        self._version = version
        edicion = "Enterprise" if meta.get("enterprise") else "Community"
        if not version:
            _log.warning("La instancia no informa su version; se continua igualmente")
            return login
        _log.info("GitLab %s (%s) en %s", version, edicion, self.vocabulary.host_label)
        numeros = _version_tuple(version)
        if numeros and numeros < MIN_VERSION:
            minima = ".".join(str(n) for n in MIN_VERSION)
            raise ScopeInaccessible(
                f"esta instancia es GitLab {version} y hace falta {minima} o posterior"
            )
        return login

    # ---- verificacion ----

    def list_scopes(self, token: Token) -> ScopeList:
        """El token por si solo: usuario, su espacio personal y sus grupos.

        Los grupos llegan con su identificador global, que es lo que luego
        filtra el sondeo: asi no hay que resolverlo despues.
        """
        login = self._check_instance(token)
        rutas: list[str] = []
        after: str | None = None
        for _ in range(GROUP_PAGES):
            body = self._send(SCOPES_QUERY, {"after": after}, token)
            usuario = ((body.get("data") or {}).get("currentUser")) or {}
            conn = usuario.get("groups") or {}
            for nodo in conn.get("nodes") or []:
                ruta, gid = nodo.get("fullPath"), nodo.get("id")
                if isinstance(ruta, str) and ruta:
                    rutas.append(ruta)
                    if isinstance(gid, str):
                        self._group_ids[ruta] = gid
            info = conn.get("pageInfo") or {}
            after = info.get("endCursor")
            if not info.get("hasNextPage") or not after:
                break
        return ScopeList(
            identity=Identity(login=login),
            scopes=(PERSONAL_PREFIX + login, *sorted(set(rutas), key=str.lower)),
        )

    def verify(self, scope: str, token: Token) -> Identity:
        kind, name = parse_scope(scope)
        login = self._check_instance(token)
        if kind == "user":
            if name.lower() != login.lower():
                raise ScopeInaccessible(f"el espacio personal del token es {login}, no {name}")
            return Identity(login=login)
        self._resolve_group(name, token)
        return Identity(login=login)

    def _resolve_group(self, ruta: str, token: Token) -> str:
        """Identificador global del grupo. GitLab responde null si no lo ve."""
        cacheado = self._group_ids.get(ruta)
        if cacheado:
            return cacheado
        body = self._send(GROUP_QUERY, {"ruta": ruta}, token)
        data = body.get("data") or {}
        grupo = data.get("group")
        if not grupo or not grupo.get("id"):
            raise ScopeInaccessible(f"el grupo {ruta} no existe o el token no tiene acceso a el")
        gid = str(grupo["id"])
        self._group_ids[ruta] = gid
        login = ((data.get("currentUser") or {}).get("username")) or ""
        if login:
            self._login = str(login)
        return gid

    # ---- listado ----

    def fetch_open(self, scope: str, token: Token) -> FetchResult:
        kind, name = parse_scope(scope)  # valida antes de tocar la red
        gid = self._resolve_group(name, token) if kind == "group" else None

        nodes: dict[str, list[dict[str, Any]]] = {alias: [] for alias in _RELATIONS}
        cursors: dict[str, str | None] = {alias: None for alias in _RELATIONS}
        pending = set(_RELATIONS)
        failed: dict[str, str] = {}
        login = self._login

        while pending:
            variables: dict[str, Any] = {"gid": gid, "n": PAGE_SIZE}
            for alias, (_, cv, iv) in _RELATIONS.items():
                variables[cv] = cursors[alias]
                variables[iv] = alias in pending
            body = self._send(WATCH_QUERY, variables, token)
            data = body.get("data") or {}
            self._log_complexity(data)
            usuario = data.get("currentUser")
            if not usuario:
                raise InvalidCredential("GitLab no devolvio el usuario del token")
            login = str(usuario.get("username") or login)
            errores = _errors_by_alias(body)
            for alias in list(pending):
                page = _page(usuario.get(alias))
                if page is None:
                    failed[alias] = errores.get(alias) or errores.get("") or "?"
                    pending.discard(alias)
                    continue
                nodes[alias].extend(page.nodes)
                if page.has_next and page.cursor:
                    cursors[alias] = page.cursor
                else:
                    pending.discard(alias)

        if len(failed) == len(_RELATIONS):
            raise NetworkError("fallaron las tres consultas: " + "; ".join(failed.values()))
        self._login = login

        by_id: dict[str, tuple[Relation, dict[str, Any]]] = {}
        for alias, (relation, *_rest) in _RELATIONS.items():
            for node in nodes[alias]:
                mr_id = node.get("id")
                if not isinstance(mr_id, str):
                    continue
                if kind == "user" and not _in_namespace(node, login):
                    continue
                current = by_id.get(mr_id)
                if current is None or relation < current[0]:
                    by_id[mr_id] = (relation, node)

        prs = [self.translate(node, relation, login) for _, (relation, node) in by_id.items()]
        return FetchResult(
            prs=prs,
            complete=not failed,
            errors=[f"{a}: {m}" for a, m in failed.items()],
        )

    def _log_complexity(self, data: dict[str, Any]) -> None:
        qc = data.get("queryComplexity") or {}
        score, limit = qc.get("score"), qc.get("limit")
        if not isinstance(score, int) or not isinstance(limit, int) or limit <= 0:
            return
        if score >= limit * COMPLEXITY_WARN:
            _log.warning("La consulta de sondeo va por %s de %s de complejidad", score, limit)

    def translate(self, node: dict[str, Any], relation: Relation, login: str) -> PullRequest:
        mr_id = str(node["id"])

        approvals = sorted(
            (
                str(n.get("username") or "?")
                for n in ((node.get("approvedBy") or {}).get("nodes") or [])
                if n
            ),
            key=str.lower,
        )

        changes_requested = False
        review_pending = False
        for revisor in (node.get("reviewers") or {}).get("nodes") or []:
            if not revisor:
                continue
            estado = ((revisor.get("mergeRequestInteraction") or {}).get("reviewState")) or ""
            if estado == "REQUESTED_CHANGES":
                changes_requested = True
            if (
                str(revisor.get("username") or "").lower() == login.lower()
                and estado in _PENDING_REVIEW
            ):
                review_pending = True

        checks = _checks((node.get("headPipeline") or {}).get("status"))

        # Mientras GitLab no haya terminado de calcular la fusionabilidad, su
        # `conflicts` no es de fiar: se conserva lo ultimo que se supo.
        if node.get("mergeStatusEnum") in ("UNCHECKED", "CHECKING"):
            conflicts = self.known_conflicts.get(mr_id)
        else:
            conflicts = bool(node.get("conflicts"))
        if conflicts is not None:
            self.known_conflicts[mr_id] = conflicts

        resolubles = int(node.get("resolvableDiscussionsCount") or 0)
        resueltas = int(node.get("resolvedDiscussionsCount") or 0)
        unresolved = max(0, resolubles - resueltas)

        draft = bool(node.get("draft"))
        # En una instancia sin reglas de aprobacion, `approved` no se vuelve
        # cierto solo: la lista de aprobadores es la senal fiable.
        approved = bool(node.get("approved")) or bool(approvals)
        ready = (
            not draft
            and conflicts is False
            and checks in (ChecksState.SUCCESS, ChecksState.NONE)
            and not changes_requested
            and approved
        )

        return PullRequest(
            id=mr_id,
            repo=str(((node.get("project") or {}).get("fullPath")) or "?"),
            number=_iid(node.get("iid")),
            title=str(node.get("title") or ""),
            url=str(node.get("webUrl") or ""),
            author=str(((node.get("author") or {}).get("username")) or "?"),
            state=_state(node.get("state")),
            draft=draft,
            relation=relation,
            approvals=tuple(approvals),
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
        """Estado por identificador, agrupando alias: no una peticion por MR."""
        result: dict[str, PrState | Inaccessible] = {}
        for start in range(0, len(ids), STATES_BATCH):
            batch = ids[start : start + STATES_BATCH]
            declaraciones = ", ".join(f"$i{k}: MergeRequestID!" for k in range(len(batch)))
            cuerpo = "\n".join(
                f"  m{k}: mergeRequest(id: $i{k}) {{ id state }}" for k in range(len(batch))
            )
            doc = f"query Estados({declaraciones}) {{\n{cuerpo}\n}}"
            variables = {f"i{k}": mr_id for k, mr_id in enumerate(batch)}
            body = self._send(doc, variables, token)
            data = body.get("data") or {}
            for k, mr_id in enumerate(batch):
                nodo = data.get(f"m{k}")
                result[mr_id] = _state(nodo.get("state")) if nodo else INACCESSIBLE
        return result

    # ---- URL ----

    def block_url(self, scope: str, relations: tuple[Relation, ...]) -> str:
        kind, name = parse_scope(scope)
        login = self._login or (name if kind == "user" else "")
        filtro = "author_username" if Relation.AUTHOR in relations else "reviewer_username"
        params = "state=opened"
        if login:
            params += f"&{filtro}={quote(login)}"
        if kind == "user":
            return f"{self.host}/dashboard/merge_requests?{params}"
        return f"{self.host}/groups/{quote(name)}/-/merge_requests?{params}"

    def scope_label(self, scope: str) -> str:
        if scope.startswith(PERSONAL_PREFIX):
            # El usuario ya sale en la fila Usuario: no se repite.
            return "Espacio personal"
        return scope

    def pr_ref(self, pr: PullRequest) -> str:
        return f"{self.vocabulary.ref_prefix}{pr.number}"

    def allows_url(self, url: str) -> bool:
        return url == self.host or url.startswith(self.host + "/")


# ---- ayudas ----


def _errors(body: dict[str, Any]) -> list[dict[str, Any]]:
    errs = body.get("errors")
    if not isinstance(errs, list):
        return []
    return [cast(dict[str, Any], e) for e in cast(list[Any], errs) if isinstance(e, dict)]


def _errors_by_alias(body: dict[str, Any]) -> dict[str, str]:
    """El alias de cada error. La ruta es `['currentUser', '<alias>', ...]`."""
    out: dict[str, str] = {}
    for err in _errors(body):
        path = err.get("path")
        alias = ""
        if isinstance(path, list):
            partes = [str(p) for p in cast(list[Any], path)]
            alias = next((p for p in partes if p in _RELATIONS), "")
        out.setdefault(alias, str(err.get("message") or "error"))
    return out


def _page(raw: Any) -> _Page | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    info = raw.get("pageInfo") or {}
    nodes = [n for n in (raw.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    return _Page(nodes=nodes, has_next=bool(info.get("hasNextPage")), cursor=info.get("endCursor"))


def _in_namespace(node: dict[str, Any], login: str) -> bool:
    """El proyecto cuelga del espacio personal del usuario.

    El ambito personal es el unico sin filtro en el servidor: las conexiones
    de `currentUser` traen todo lo del usuario en la instancia.
    """
    ruta = str(((node.get("project") or {}).get("fullPath")) or "")
    return bool(login) and ruta.split("/", 1)[0].lower() == login.lower()


def _rate_limit(headers: Any) -> RateLimited:
    """Cuando vuelve a haber cupo. Esta instancia no siempre lo dice."""
    h = {k.lower(): v for k, v in dict(headers).items()}
    now = datetime.now(UTC)
    retry_after = h.get("retry-after", "")
    if retry_after.isdigit():
        return RateLimited(now + timedelta(seconds=int(retry_after)))
    reset = h.get("ratelimit-reset", "")
    if reset.isdigit():
        return RateLimited(datetime.fromtimestamp(int(reset), UTC))
    return RateLimited(now + timedelta(minutes=1))


def _version_tuple(version: str) -> tuple[int, ...]:
    partes: list[int] = []
    for trozo in version.split("-")[0].split(".")[:3]:
        if not trozo.isdigit():
            break
        partes.append(int(trozo))
    return tuple(partes)


def _iid(raw: Any) -> int:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0


def _checks(status: Any) -> ChecksState:
    match status:
        case "SUCCESS":
            return ChecksState.SUCCESS
        case "FAILED" | "CANCELED" | "CANCELING":
            return ChecksState.FAILURE
        case (
            "CREATED"
            | "WAITING_FOR_RESOURCE"
            | "WAITING_FOR_CALLBACK"
            | "PREPARING"
            | "PENDING"
            | "RUNNING"
            | "SCHEDULED"
        ):
            return ChecksState.PENDING
        case _:
            # SKIPPED, MANUAL o sin pipeline: no hay nada que esperar.
            return ChecksState.NONE


def _state(raw: Any) -> PrState:
    match raw:
        case "merged":
            return PrState.MERGED
        case "closed":
            return PrState.CLOSED
        case _:
            # `locked` es una discusion cerrada, no el MR: sigue abierto.
            return PrState.OPEN


def _parse_time(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, UTC)


def _check_main() -> int:
    """Diagnostico: `python -m pr_watch.providers.gitlab --check`.

    Verifica la credencial guardada contra el ambito configurado e imprime un
    resumen de lo que llega, sin mostrar el token.
    """
    from pr_watch import config as config_mod
    from pr_watch.credential import CredentialStore, system_keyring

    cfg = config_mod.load(config_mod.config_dir() / config_mod.CONFIG_FILE).config
    if not cfg.gitlab.host:
        print("No hay host de GitLab configurado.")
        return 2
    gl = GitLabProvider(cfg.gitlab.host)
    store = CredentialStore(
        gl.instance_key, config_mod.config_dir(), keyring_backend=system_keyring()
    )
    loaded = store.load()
    if loaded is None:
        print("No hay token: define PR_WATCH_TOKEN o configuralo en la aplicacion.")
        return 2
    scope = cfg.scope()
    print(f"Instancia: {gl.host} · ambito: {scope or '(sin configurar)'}")
    print(f"Token desde {loaded.source.value} · clave {gl.instance_key}")
    try:
        ident = gl.verify(scope, loaded.token)
        print(f"Conectado como {ident.login}")
        result = gl.fetch_open(scope, loaded.token)
    except ProviderError as e:
        print(f"Error ({type(e).__name__}): {e}")
        return 1
    print(f"Completo: {result.complete} {result.errors}")
    for pr in sorted(result.prs, key=lambda p: (p.relation, p.repo, p.number)):
        print(
            f"  [{pr.relation.name:8}] {pr.repo}!{pr.number} draft={pr.draft} "
            f"aprob={list(pr.approvals)} cambios={pr.changes_requested} checks={pr.checks} "
            f"conflictos={pr.conflicts} sin_resolver={pr.unresolved} listo={pr.ready_to_merge}"
        )
    sin_checks = sum(1 for p in result.prs if p.checks is ChecksState.NONE)
    print(f"MR sin pipeline: {sin_checks} de {len(result.prs)}")
    return 0


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        sys.exit(_check_main())
    print("Uso: python -m pr_watch.providers.gitlab --check")
