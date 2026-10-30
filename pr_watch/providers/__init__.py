"""Registro de proveedores de forja. Anadir uno = un modulo y una entrada aqui.

La fabrica recibe la configuracion, no solo un nombre: un proveedor que vive
en varias instancias (GitLab) necesita saber contra cual habla.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pr_watch.config import Config
from pr_watch.providers.base import Provider
from pr_watch.providers.github import GitHubProvider
from pr_watch.providers.gitlab import GitLabProvider


@dataclass(frozen=True, slots=True)
class Entry:
    display_name: str
    # True si la forja vive en varias instancias y hay que configurar el host.
    needs_host: bool
    # Devuelve None si la configuracion no basta (host inservible).
    build: Callable[[Config], Provider | None]


REGISTRY: dict[str, Entry] = {
    "github": Entry(GitHubProvider.DISPLAY_NAME, False, lambda cfg: GitHubProvider()),
    "gitlab": Entry(
        GitLabProvider.DISPLAY_NAME,
        True,
        lambda cfg: GitLabProvider(cfg.gitlab.host) if cfg.gitlab.host else None,
    ),
}


def create(cfg: Config) -> Provider | None:
    entry = REGISTRY.get(cfg.provider)
    return entry.build(cfg) if entry else None
