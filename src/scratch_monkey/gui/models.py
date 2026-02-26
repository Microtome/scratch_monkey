"""Atom-based observable models for the scratch-monkey GUI."""

from __future__ import annotations

from pathlib import Path

try:
    from atom.api import Atom, Bool, List, Str, Value
except ImportError:
    raise ImportError(
        "The GUI requires the 'enaml' package. "
        "Install it with: pip install 'scratch-monkey[gui]'"
    )

from ..config import InstanceConfig, save
from ..container import PodmanRunner
from ..instance import InstanceInfo, list_all


class InstanceModel(Atom):
    """Observable model for a single scratch-monkey instance."""

    name = Str()
    directory = Str()
    image_built = Bool(False)
    overlay_running = Bool(False)

    # Config fields
    cmd = Str("/bin/bash")
    wayland = Bool(False)
    ssh = Bool(False)
    home = Str("")
    overlay = Bool(False)
    shared = List(str)
    volumes = List(str)
    env_vars = List(str)

    @classmethod
    def from_info(cls, info: InstanceInfo) -> InstanceModel:
        m = cls()
        m.name = info.name
        m.directory = str(info.directory)
        m.image_built = info.image_built
        m.overlay_running = info.overlay_running
        cfg = info.config
        m.cmd = cfg.cmd
        m.wayland = cfg.wayland
        m.ssh = cfg.ssh
        m.home = cfg.home
        m.overlay = cfg.overlay
        m.shared = list(cfg.shared)
        m.volumes = list(cfg.volumes)
        m.env_vars = list(cfg.env)
        return m

    def to_config(self) -> InstanceConfig:
        return InstanceConfig(
            cmd=self.cmd,
            wayland=self.wayland,
            ssh=self.ssh,
            home=self.home,
            volumes=list(self.volumes),
            env=list(self.env_vars),
            shared=list(self.shared),
            overlay=self.overlay,
        )

    def save(self) -> None:
        """Persist the current model state to scratch.toml."""
        config_path = Path(self.directory) / "scratch.toml"
        save(config_path, self.to_config())


class AppModel(Atom):
    """Root application model for the scratch-monkey GUI."""

    instances_dir = Str()
    instances = List(InstanceModel)
    selected_instance = Str("")  # name of selected instance
    status_message = Str("")
    # PodmanRunner stored as a Value member so Atom allows it
    _runner = Value()

    def __init__(self, instances_dir: Path, runner: PodmanRunner | None = None) -> None:
        super().__init__()
        self.instances_dir = str(instances_dir)
        self._runner = runner or PodmanRunner()
        self.refresh()

    def refresh(self) -> None:
        """Reload all instances from disk."""
        instances_dir = Path(self.instances_dir)
        try:
            infos = list_all(instances_dir, self._runner)
            self.instances = [InstanceModel.from_info(i) for i in infos]
            self.status_message = f"Loaded {len(self.instances)} instance(s)"
        except Exception as e:
            self.status_message = f"Error loading instances: {e}"

    @property
    def selected(self) -> InstanceModel | None:
        for inst in self.instances:
            if inst.name == self.selected_instance:
                return inst
        return None
