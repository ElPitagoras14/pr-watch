"""Credencial del proveedor: keyring del sistema con respaldo a archivo.

Orden de lectura: variable de entorno, `.env` del directorio de trabajo,
keyring y archivo de respaldo. `GITHUB_TOKEN` y `GH_TOKEN` se ignoran a
proposito: suelen llevar permisos de escritura que esta herramienta no debe
tener.

Todo se guarda bajo la clave que declara el proveedor, que incluye la
instancia cuando la forja vive en varias: dos instancias de GitLab no se
pisan el token. Tambien la variable de desarrollo, que si fuera unica daria
el token de una instancia a otra al conmutar.
"""

from __future__ import annotations

import enum
import logging
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pr_watch import log

SERVICE = "pr-watch"
ENV_VAR = "PR_WATCH_TOKEN"

_log = logging.getLogger(__name__)


def env_var_for(key: str) -> str:
    """`gitlab@gitlab-telconet-ec` -> `PR_WATCH_TOKEN_GITLAB_GITLAB_TELCONET_EC`."""
    return f"{ENV_VAR}_{re.sub(r'[^A-Za-z0-9]+', '_', key).upper().strip('_')}"


class Token:
    """Un token que no se deja imprimir.

    `repr` y `str` lo ocultan, para que un `log.info("%s", token)` o una
    excepcion con el token dentro no lo filtren. El valor solo sale con
    `reveal()`, y solo el cliente HTTP lo llama.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value.strip()
        log.register_secret(self._value)

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Token) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return "Token(<oculto>)"

    __str__ = __repr__


class Source(enum.Enum):
    ENV = "variable de entorno"
    DOTENV = ".env"
    KEYRING = "almacen de credenciales"
    FILE = "archivo en texto plano"


@dataclass(frozen=True, slots=True)
class Loaded:
    token: Token
    source: Source


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def system_keyring() -> KeyringBackend | None:
    """El keyring del sistema, o None si no hay ninguno utilizable."""
    try:
        import keyring
        from keyring.backends import chainer, fail

        kr = keyring.get_keyring()
        if isinstance(kr, fail.Keyring):
            return None
        if isinstance(kr, chainer.ChainerBackend) and not kr.backends:
            return None
        return cast(KeyringBackend, kr)
    except Exception as e:
        _log.warning("No hay almacen de credenciales disponible: %s", type(e).__name__)
        return None


class CredentialStore:
    def __init__(
        self,
        key: str,
        config_dir: Path,
        *,
        cwd: Path | None = None,
        environ: Mapping[str, str] | None = None,
        keyring_backend: KeyringBackend | None = None,
    ) -> None:
        # La clave la declara el proveedor: `github`, `gitlab@<instancia>`.
        self.key = key
        self.config_dir = config_dir
        self.cwd = cwd if cwd is not None else Path.cwd()
        self.environ = environ if environ is not None else os.environ
        self.keyring = keyring_backend

    @property
    def fallback_file(self) -> Path:
        return self.config_dir / f"token-{self.key}"

    @property
    def env_var(self) -> str:
        """La variable propia de esta forja; la generica sigue valiendo."""
        return env_var_for(self.key)

    def keyring_available(self) -> bool:
        return self.keyring is not None

    # ---- lectura ----

    def load(self) -> Loaded | None:
        for nombre in (self.env_var, ENV_VAR):
            value = self.environ.get(nombre, "").strip()
            if value:
                return Loaded(Token(value), Source.ENV)

        value = self._from_dotenv()
        if value:
            return Loaded(Token(value), Source.DOTENV)

        value = self._from_keyring()
        if value:
            return Loaded(Token(value), Source.KEYRING)

        value = self._from_file()
        if value:
            token = Token(value)
            # Si el keyring aparecio despues, se pasa ahi y se deja de depender
            # del archivo en texto plano.
            if self.keyring is not None and self._to_keyring(token):
                self._delete_file()
                return Loaded(token, Source.KEYRING)
            return Loaded(token, Source.FILE)
        return None

    def _from_dotenv(self) -> str:
        path = self.cwd / ".env"
        try:
            lines = path.read_text("utf-8").splitlines()
        except OSError:
            return ""
        encontrado: dict[str, str] = {}
        for line in lines:
            key, sep, value = line.strip().partition("=")
            nombre = key.strip().removeprefix("export ").strip()
            if sep and nombre in (self.env_var, ENV_VAR):
                encontrado[nombre] = value.strip().strip("'\"").strip()
        return encontrado.get(self.env_var) or encontrado.get(ENV_VAR, "")

    def _from_keyring(self) -> str:
        if self.keyring is None:
            return ""
        try:
            return (self.keyring.get_password(SERVICE, self.key) or "").strip()
        except Exception as e:
            _log.warning("No se pudo leer del almacen de credenciales: %s", type(e).__name__)
            return ""

    def _from_file(self) -> str:
        try:
            return self.fallback_file.read_text("utf-8").strip()
        except OSError:
            return ""

    # ---- escritura ----

    def save(self, token: Token) -> Source:
        """Guarda el token. Devuelve donde quedo: keyring o archivo."""
        if self.keyring is not None and self._to_keyring(token):
            self._delete_file()
            return Source.KEYRING
        self._to_file(token)
        _log.warning(
            "El token quedo en texto plano en %s: no hay almacen de credenciales",
            self.fallback_file,
        )
        return Source.FILE

    def _to_keyring(self, token: Token) -> bool:
        assert self.keyring is not None
        try:
            self.keyring.set_password(SERVICE, self.key, token.reveal())
            return True
        except Exception as e:
            _log.warning("No se pudo guardar en el almacen de credenciales: %s", type(e).__name__)
            return False

    def _to_file(self, token: Token) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self.fallback_file
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, token.reveal().encode("utf-8"))
        finally:
            os.close(fd)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    # ---- borrado ----

    def delete(self) -> None:
        """Borra la credencial del keyring y del archivo. Nada que borrar no es error."""
        if self.keyring is not None:
            try:
                if self.keyring.get_password(SERVICE, self.key) is not None:
                    self.keyring.delete_password(SERVICE, self.key)
            except Exception as e:
                _log.warning("No se pudo borrar del almacen de credenciales: %s", type(e).__name__)
        self._delete_file()

    def _delete_file(self) -> None:
        try:
            self.fallback_file.unlink()
        except FileNotFoundError:
            pass

    def has_stored(self) -> bool:
        """Hay credencial guardada por la aplicacion (keyring o archivo)."""
        return bool(self._from_keyring() or self._from_file())
