"""Shared volume management for scratch-monkey instances."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import load, save
from .instance import Instance


class SharedError(Exception):
    """Raised for shared volume operation errors."""


def _shared_dir(instances_dir: Path, name: str) -> Path:
    return instances_dir / ".shared" / name


def parse_shared_entry(entry: str) -> tuple[str, str]:
    """Parse 'name' or 'name:ro' -> (name, mode). Default mode is 'rw'."""
    if ":" in entry:
        name, mode = entry.rsplit(":", 1)
        if mode not in ("ro", "rw"):
            raise SharedError(
                f"Invalid shared volume mode {mode!r} in {entry!r}. "
                "Use 'ro' or 'rw'."
            )
        return name, mode
    return entry, "rw"


def create_shared(name: str, instances_dir: Path) -> Path:
    """Create a shared volume directory.

    Returns the path to the new shared volume.
    Raises SharedError if it already exists.
    """
    instances_dir = Path(instances_dir)
    vol_dir = _shared_dir(instances_dir, name)
    if vol_dir.exists():
        raise SharedError(
            f"Shared volume {name!r} already exists at {vol_dir}"
        )
    vol_dir.mkdir(parents=True)
    return vol_dir


def delete_shared(name: str, instances_dir: Path) -> None:
    """Delete a shared volume directory.

    Also removes the volume from all instance configs atomically.
    Raises SharedError if the volume does not exist.
    """
    instances_dir = Path(instances_dir)
    vol_dir = _shared_dir(instances_dir, name)
    if not vol_dir.exists():
        raise SharedError(
            f"Shared volume {name!r} not found at {vol_dir}"
        )

    # Remove from all instance configs
    for entry in sorted(instances_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        config_path = entry / "scratch.toml"
        if not config_path.exists():
            continue
        cfg = load(config_path)
        if name in cfg.shared:
            cfg.shared = [v for v in cfg.shared if v != name]
            save(config_path, cfg)

    shutil.rmtree(vol_dir)


def add_to_instance(vol_name: str, instance: Instance, instances_dir: Path) -> None:
    """Add a shared volume to an instance's config.

    Raises SharedError if the shared volume does not exist.
    Does nothing if the volume is already in the config.
    """
    instances_dir = Path(instances_dir)
    vol_dir = _shared_dir(instances_dir, vol_name)
    if not vol_dir.exists():
        raise SharedError(
            f"Shared volume {vol_name!r} does not exist. "
            f"Create it first with: scratch-monkey share create {vol_name}"
        )

    config_path = instance.directory / "scratch.toml"
    cfg = load(config_path)
    if vol_name in cfg.shared:
        return  # already present
    cfg.shared = [*cfg.shared, vol_name]
    save(config_path, cfg)
    instance.config = cfg


def remove_from_instance(vol_name: str, instance: Instance) -> bool:
    """Remove a shared volume from an instance's config.

    Returns True if it was removed, False if it wasn't in the config.
    """
    config_path = instance.directory / "scratch.toml"
    cfg = load(config_path)
    if vol_name not in cfg.shared:
        return False
    cfg.shared = [v for v in cfg.shared if v != vol_name]
    save(config_path, cfg)
    instance.config = cfg
    return True


@dataclass
class SharedVolumeInfo:
    """Info about a shared volume."""

    name: str
    path: Path
    used_by: list[str]


def list_shared(instances_dir: Path) -> list[SharedVolumeInfo]:
    """List all shared volumes and which instances use them."""
    instances_dir = Path(instances_dir)
    shared_base = instances_dir / ".shared"

    if not shared_base.is_dir():
        return []

    # Build a map of volume → instances
    volume_users: dict[str, list[str]] = {}
    for vol_dir in sorted(shared_base.iterdir()):
        if vol_dir.is_dir():
            volume_users[vol_dir.name] = []

    for entry in sorted(instances_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        config_path = entry / "scratch.toml"
        if not config_path.exists():
            continue
        cfg = load(config_path)
        for vol_name in cfg.shared:
            if vol_name in volume_users:
                volume_users[vol_name].append(entry.name)

    return [
        SharedVolumeInfo(
            name=name,
            path=shared_base / name,
            used_by=users,
        )
        for name, users in volume_users.items()
    ]
