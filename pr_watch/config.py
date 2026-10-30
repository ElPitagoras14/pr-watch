"""Configuracion: `config.toml` en el directorio del usuario.

La lectura nunca aborta: un archivo ilegible se conserva intacto y se usan los
valores por defecto; una clave desconocida se ignora; un valor fuera de rango
se corrige al extremo mas cercano. Cada correccion deja un aviso.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

APP_ID = "pr-watch"
CONFIG_FILE = "config.toml"

MIN_INTERVAL_SECS = 30
MIN_PER_BLOCK = 1
MAX_PER_BLOCK = 20


def config_dir() -> Path:
    """Directorio de configuracion de la aplicacion.

    `PR_WATCH_CONFIG_DIR` lo sustituye, para pruebas y para desarrollar sin
    tocar la configuracion real.
    """
    override = os.environ.get("PR_WATCH_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_ID
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_ID


# Prefijo del ambito "cuenta personal": `user:<login>` en lugar de una organizacion.
PERSONAL_PREFIX = "user:"


@dataclass(slots=True)
class GitHubSettings:
    # Uno de los dos: la organizacion vigilada o la cuenta personal.
    org: str = ""
    user: str = ""


@dataclass(slots=True)
class Config:
    provider: str = "github"
    poll_interval_secs: int = 60
    max_per_block: int = 5
    closed_ttl_minutes: int = 15
    notifications: bool = False
    github: GitHubSettings = field(default_factory=GitHubSettings)

    def scope(self) -> str:
        """El ambito del proveedor activo: en GitHub, la organizacion."""
        match self.provider:
            case "github":
                if self.github.user:
                    return PERSONAL_PREFIX + self.github.user
                return self.github.org
            case _:
                return ""

    def with_scope(self, scope: str) -> Config:
        nuevo = clone(self)
        if nuevo.provider == "github":
            scope = scope.strip()
            if scope.startswith(PERSONAL_PREFIX):
                nuevo.github.user = scope.removeprefix(PERSONAL_PREFIX).strip()
                nuevo.github.org = ""
            else:
                nuevo.github.org = scope
                nuevo.github.user = ""
        return nuevo


def clone(cfg: Config) -> Config:
    return from_dict(to_dict(cfg))[0]


@dataclass(slots=True)
class LoadResult:
    config: Config
    warnings: list[str]
    # False si el archivo existia pero no se pudo interpretar: en ese caso no
    # se debe sobrescribir sin que el usuario lo pida.
    file_ok: bool = True


def to_dict(cfg: Config) -> dict[str, Any]:
    return {
        "provider": cfg.provider,
        "poll_interval_secs": cfg.poll_interval_secs,
        "max_per_block": cfg.max_per_block,
        "closed_ttl_minutes": cfg.closed_ttl_minutes,
        "notifications": cfg.notifications,
        "github": {"org": cfg.github.org, "user": cfg.github.user},
    }


def _int(data: dict[str, Any], key: str, default: int, warnings: list[str]) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        warnings.append(f"`{key}` no es un numero entero; se usa {default}")
        return default
    return value


def from_dict(data: dict[str, Any]) -> tuple[Config, list[str]]:
    """Construye la configuracion desde un dict ya parseado, corrigiendo rangos."""
    warnings: list[str] = []
    cfg = Config()

    provider = data.get("provider", cfg.provider)
    if isinstance(provider, str) and provider.strip():
        cfg.provider = provider.strip()
    else:
        warnings.append("`provider` no es valido; se usa github")

    interval = _int(data, "poll_interval_secs", cfg.poll_interval_secs, warnings)
    if interval < MIN_INTERVAL_SECS:
        warnings.append(
            f"`poll_interval_secs` = {interval} esta por debajo del suelo; "
            f"se usa {MIN_INTERVAL_SECS}"
        )
        interval = MIN_INTERVAL_SECS
    cfg.poll_interval_secs = interval

    per_block = _int(data, "max_per_block", cfg.max_per_block, warnings)
    clamped = min(max(per_block, MIN_PER_BLOCK), MAX_PER_BLOCK)
    if clamped != per_block:
        warnings.append(f"`max_per_block` = {per_block} fuera de rango; se usa {clamped}")
    cfg.max_per_block = clamped

    ttl = _int(data, "closed_ttl_minutes", cfg.closed_ttl_minutes, warnings)
    if ttl < 0:
        warnings.append(f"`closed_ttl_minutes` = {ttl} es negativo; se usa 0")
        ttl = 0
    cfg.closed_ttl_minutes = ttl

    notifications = data.get("notifications", cfg.notifications)
    if isinstance(notifications, bool):
        cfg.notifications = notifications
    else:
        warnings.append("`notifications` no es true/false; se usa false")

    github = data.get("github", {})
    if isinstance(github, dict):
        for key in ("org", "user"):
            value = github.get(key, "")
            if isinstance(value, str):
                setattr(cfg.github, key, value.strip())
            else:
                warnings.append(f"`github.{key}` no es texto; se ignora")
        if cfg.github.org and cfg.github.user:
            warnings.append("`github.org` y `github.user` a la vez: se usa la organizacion")
            cfg.github.user = ""
    else:
        warnings.append("`[github]` no es una tabla; se ignora")

    return cfg, warnings


def load(path: Path) -> LoadResult:
    """Lee `config.toml`; si no existe lo crea con los valores por defecto."""
    if not path.exists():
        cfg = Config()
        warnings: list[str] = []
        try:
            save(cfg, path)
        except OSError as e:
            warnings.append(f"No se pudo crear {path}: {e}")
        return LoadResult(cfg, warnings)

    try:
        data = tomllib.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return LoadResult(
            Config(),
            [f"{path} no se pudo leer ({e}); se usan los valores por defecto"],
            file_ok=False,
        )

    cfg, warnings = from_dict(data)
    return LoadResult(cfg, warnings)


def save(cfg: Config, path: Path) -> None:
    """Escribe la configuracion de forma atomica. Lanza OSError si no puede."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(tomli_w.dumps(to_dict(cfg)), "utf-8")
    os.replace(tmp, path)
