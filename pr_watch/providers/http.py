"""Transporte HTTP comun a los proveedores.

Una sola funcion de envio, inyectable: las pruebas pasan la suya y ningun
proveedor abre conexiones por su cuenta. Las CA son las del sistema, para que
una instancia detras de una CA corporativa valide sin configuracion extra.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

from pr_watch.providers.base import NetworkError

_FORBIDDEN_OP = re.compile(r"\b(mutation|subscription)\b")
_STRINGS = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"')
_COMMENTS = re.compile(r"#[^\n]*")


def assert_read_only(document: str) -> None:
    """Rechaza cualquier documento GraphQL que no sea una consulta."""
    stripped = _COMMENTS.sub("", _STRINGS.sub('""', document))
    if _FORBIDDEN_OP.search(stripped):
        raise AssertionError("pr-watch es de solo lectura: documento GraphQL rechazado")


class Response(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def json(self) -> Any: ...


# (url, cuerpo, cabeceras, timeout). Cuerpo None = GET de una API REST; con
# cuerpo = POST de una consulta GraphQL. No hay otros verbos.
type Transport = Callable[[str, dict[str, Any] | None, dict[str, str], float], Response]


def requests_transport(user_agent: str = "pr-watch") -> Transport:
    """Transporte real: una sesion de requests con las CA del sistema."""
    import requests
    import truststore

    truststore.inject_into_ssl()
    session = requests.Session()
    session.headers["User-Agent"] = user_agent

    def send(
        url: str, body: dict[str, Any] | None, headers: dict[str, str], timeout: float
    ) -> Response:
        try:
            if body is None:
                return cast(Response, session.get(url, headers=headers, timeout=timeout))
            return cast(Response, session.post(url, json=body, headers=headers, timeout=timeout))
        except requests.RequestException as e:
            raise NetworkError(type(e).__name__) from None

    return send
