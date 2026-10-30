"""Modelo neutro de pull request y contrato que cumple cada proveedor de forja.

Nada fuera de `providers/` conoce GitHub: el sondeo, el panel, la bandeja y las
notificaciones trabajan solo con lo que hay aqui.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pr_watch.credential import Token


class Relation(enum.IntEnum):
    """Relacion del usuario con el PR. Menor valor = mayor prioridad."""

    AUTHOR = 0
    REVIEWER = 1
    ASSIGNEE = 2


class ChecksState(enum.StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NONE = "none"


class PrState(enum.StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class PullRequest:
    id: str  # estable y unico en la forja
    repo: str
    number: int
    title: str
    url: str
    author: str
    state: PrState
    draft: bool
    relation: Relation
    approvals: tuple[str, ...]  # logins de quienes aprobaron
    changes_requested: bool
    checks: ChecksState
    # None = la forja todavia no lo sabe; el sondeo conserva el valor anterior.
    conflicts: bool | None
    unresolved: int
    ready_to_merge: bool
    # La revision del usuario sigue pendiente (vino por "revision solicitada").
    review_pending: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Identity:
    login: str


@dataclass(frozen=True, slots=True)
class ScopeList:
    """Lo que ve un token por si solo: quien es y que ambitos puede elegir."""

    identity: Identity
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FetchResult:
    prs: list[PullRequest]
    # False si alguna relacion fallo: con datos incompletos no se purga nada.
    complete: bool
    # Una linea por relacion que fallo, para el registro.
    errors: list[str] = field(default_factory=list[str])


class Inaccessible(enum.Enum):
    INACCESSIBLE = "inaccessible"


INACCESSIBLE = Inaccessible.INACCESSIBLE


@dataclass(frozen=True, slots=True)
class Vocabulary:
    noun: str  # "PR"
    ref_prefix: str  # "#"
    host_label: str  # "github.com"


@dataclass(frozen=True, slots=True)
class Descriptor:
    """Lo que la ventana de ajustes necesita saber de la forja activa.

    Sin esto la ventana tendria que nombrar a GitHub a fuego: los permisos que
    pedir, donde se crea el token y como se llama el ambito cambian con cada
    forja.
    """

    display_name: str  # "GitHub", "GitLab"
    scope_label: str  # "Cuenta u organizacion", "Grupo o espacio personal"
    scope_placeholder: str  # que poner cuando el ambito se escribe a mano
    token_permissions: tuple[str, ...]  # permisos de solo lectura a pedir
    create_token_url: str
    # True si la forja vive en varias instancias y el host se configura.
    configurable_host: bool


# ---- errores clasificados ----


class ProviderError(Exception):
    """Base de los errores que un proveedor puede devolver."""


class InvalidCredential(ProviderError):
    pass


class ScopeInaccessible(ProviderError):
    pass


class RateLimited(ProviderError):
    def __init__(self, reset_at: datetime, message: str = "") -> None:
        super().__init__(message or f"limite agotado hasta {reset_at.isoformat()}")
        self.reset_at = reset_at


class NetworkError(ProviderError):
    pass


class Provider(Protocol):
    name: str
    vocabulary: Vocabulary

    @property
    def instance_key(self) -> str:
        """Clave con la que se guardan credencial y estado de esta forja.

        Una forja de instancia unica devuelve su nombre (`github`); una que
        vive en varias instancias lo compone con la suya
        (`gitlab@gitlab-telconet-ec`), para que dos instancias no se pisen.
        """
        ...

    @property
    def descriptor(self) -> Descriptor: ...

    def list_scopes(self, token: Token) -> ScopeList: ...

    def verify(self, scope: str, token: Token) -> Identity: ...

    def fetch_open(self, scope: str, token: Token) -> FetchResult: ...

    def fetch_states(self, ids: list[str], token: Token) -> dict[str, PrState | Inaccessible]: ...

    def block_url(self, scope: str, relations: tuple[Relation, ...]) -> str: ...

    def pr_ref(self, pr: PullRequest) -> str: ...

    def scope_label(self, scope: str) -> str: ...

    def allows_url(self, url: str) -> bool: ...
