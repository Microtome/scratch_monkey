"""TOML config read/write for scratch-monkey instances."""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Default location for instance directories
DEFAULT_INSTANCES_DIR: Path = Path.home() / "scratch-monkey"

# Valid instance name: starts with alphanum, then alphanum/underscore/dot/dash
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")


class ConfigError(Exception):
    """Raised for config validation or parse errors."""


def validate_name(name: str) -> None:
    """Raise ConfigError if name is not a valid instance name."""
    if not _NAME_RE.match(name):
        raise ConfigError(
            f"Invalid instance name {name!r}. "
            "Must start with alphanumeric and contain only "
            "alphanumeric, underscore, dot, or dash."
        )


@dataclass
class InstanceConfig:
    """Typed representation of a scratch.toml instance config."""

    cmd: str = "/bin/bash"
    wayland: bool = False
    ssh: bool = False
    home: str = ""
    volumes: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)
    overlay: bool = False


def load(path: Path) -> InstanceConfig:
    """Parse a scratch.toml file and return an InstanceConfig.

    Missing keys use their dataclass defaults.
    """
    path = Path(path)
    if not path.exists():
        return InstanceConfig()

    with path.open("rb") as f:
        data = tomllib.load(f)

    def _bool(val: object) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def _strlist(val: object) -> list[str]:
        if isinstance(val, list):
            return [str(v) for v in val]
        return []

    return InstanceConfig(
        cmd=str(data.get("cmd", "/bin/bash")),
        wayland=_bool(data.get("wayland", False)),
        ssh=_bool(data.get("ssh", False)),
        home=str(data.get("home", "")),
        volumes=_strlist(data.get("volumes", [])),
        env=_strlist(data.get("env", [])),
        shared=_strlist(data.get("shared", [])),
        overlay=_bool(data.get("overlay", False)),
    )


def save(path: Path, config: InstanceConfig) -> None:
    """Atomically write an InstanceConfig to a scratch.toml file.

    Writes to a temp file in the same directory, then renames.
    """
    path = Path(path)
    content = _serialize(config)
    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".scratch-monkey-", suffix=".toml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _serialize(config: InstanceConfig) -> str:
    """Convert an InstanceConfig to TOML text."""
    lines = ["# scratch-monkey instance configuration\n"]

    def _toml_str(s: str) -> str:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _toml_strlist(lst: list[str]) -> str:
        items = ", ".join(_toml_str(v) for v in lst)
        return f"[{items}]"

    lines.append(f"cmd = {_toml_str(config.cmd)}\n")
    lines.append(f"wayland = {str(config.wayland).lower()}\n")
    lines.append(f"ssh = {str(config.ssh).lower()}\n")

    if config.home:
        lines.append(f"home = {_toml_str(config.home)}\n")
    else:
        lines.append('home = ""\n')

    lines.append(f"volumes = {_toml_strlist(config.volumes)}\n")
    lines.append(f"env = {_toml_strlist(config.env)}\n")
    lines.append(f"shared = {_toml_strlist(config.shared)}\n")
    lines.append(f"overlay = {str(config.overlay).lower()}\n")

    return "".join(lines)
