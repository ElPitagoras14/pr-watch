"""Registro de proveedores de forja. Anadir uno = un modulo y una entrada aqui."""

from __future__ import annotations

from collections.abc import Callable

from pr_watch.providers.base import Provider
from pr_watch.providers.github import GitHubProvider

REGISTRY: dict[str, Callable[[], Provider]] = {
    "github": GitHubProvider,
}


def create(name: str) -> Provider | None:
    factory = REGISTRY.get(name)
    return factory() if factory else None
