"""Atom-based observable models for the scratch-monkey GUI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

try:
    from atom.api import Atom, Bool, List, Str, Value
except ImportError:
    raise ImportError(
        "The GUI requires the 'enaml' package. "
        "Install it with: uv tool install 'scratch-monkey[gui]'"
    )

from ..config import ConfigError, InstanceConfig, save
from ..container import PodmanRunner
from ..instance import InstanceError, InstanceInfo, create, list_all, skel_copy
from ..shared import list_shared, parse_shared_entry

_PROJECT_DIR = Path(__file__).parent.parent.parent.parent
_DEFAULT_BASE_IMAGE = "scratch_dev"
_FEDORA_IMAGE = "scratch_dev_fedora"


def _find_terminal() -> list[str]:
    """Return a command prefix to launch a terminal emulator.

    Tries xdg-terminal-exec first (standard portable method), then
    common terminals. Returns an empty list if none are found.
    """
    candidates = [
        (["xdg-terminal-exec"], []),
        (["gnome-terminal"], ["--"]),
        (["konsole"], ["-e"]),
        (["xfce4-terminal"], ["-e"]),
        (["alacritty"], ["-e"]),
        (["kitty"], []),
        (["foot"], []),
        (["xterm"], ["-e"]),
    ]
    for base, sep in candidates:
        if shutil.which(base[0]):
            return base + sep
    return []


def _launch_in_terminal(cmd: list[str]) -> str:
    """Launch cmd in a terminal emulator. Returns an error string or ''."""
    prefix = _find_terminal()
    if not prefix:
        return "No terminal emulator found. Install xdg-terminal-exec, gnome-terminal, or similar."
    subprocess.Popen([*prefix, *cmd])
    return ""


class VolumeMountEntry(Atom):
    """Structured representation of a volume mount string like '/host:/container:ro'."""

    host_path = Str()
    container_path = Str()
    mode = Str("rw")

    @classmethod
    def from_spec(cls, spec: str) -> VolumeMountEntry:
        """Parse a volume spec string like '/host:/container' or '/host:/container:ro'."""
        parts = spec.split(":")
        if len(parts) == 3:
            return cls(host_path=parts[0], container_path=parts[1], mode=parts[2])
        elif len(parts) == 2:
            return cls(host_path=parts[0], container_path=parts[1], mode="rw")
        else:
            return cls(host_path=spec, container_path=spec, mode="rw")

    def to_spec(self) -> str:
        """Serialize back to a volume spec string."""
        if self.mode == "rw":
            return f"{self.host_path}:{self.container_path}"
        return f"{self.host_path}:{self.container_path}:{self.mode}"


class SharedVolumeEntry(Atom):
    """A shared volume with enabled/disabled state and mode."""

    name = Str()
    enabled = Bool(False)
    mode = Str("rw")


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
    volume_entries = List(VolumeMountEntry)
    shared_entries = List(SharedVolumeEntry)

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
        m.volume_entries = [VolumeMountEntry.from_spec(v) for v in cfg.volumes]
        return m

    def to_config(self) -> InstanceConfig:
        return InstanceConfig(
            cmd=self.cmd,
            wayland=self.wayland,
            ssh=self.ssh,
            home=self.home,
            volumes=[e.to_spec() for e in self.volume_entries],
            env=list(self.env_vars),
            shared=[
                f"{e.name}:{e.mode}" if e.mode != "rw" else e.name
                for e in self.shared_entries
                if e.enabled
            ],
            overlay=self.overlay,
        )

    def add_volume_entry(self) -> None:
        """Append a new blank volume mount entry."""
        self.volume_entries = [*self.volume_entries, VolumeMountEntry()]

    def remove_volume_entry(self, index: int) -> None:
        """Remove volume entry at the given index."""
        entries = list(self.volume_entries)
        if 0 <= index < len(entries):
            del entries[index]
            self.volume_entries = entries

    def add_env_var(self, value: str = "") -> None:
        """Append a new environment variable entry."""
        self.env_vars = [*self.env_vars, value]

    def remove_env_var(self, index: int) -> None:
        """Remove env var at the given index."""
        entries = list(self.env_vars)
        if 0 <= index < len(entries):
            del entries[index]
            self.env_vars = entries

    def save(self) -> None:
        """Persist the current model state to scratch.toml."""
        config_path = Path(self.directory) / "scratch.toml"
        save(config_path, self.to_config())


class AppModel(Atom):
    """Root application model for the scratch-monkey GUI."""

    instances_dir = Str()
    instances = List(InstanceModel)
    selected_instance = Str("")
    # selected is an observable Value member kept in sync with selected_instance.
    # Using Value() (not @property) so Enaml bindings re-fire when it changes.
    selected = Value()
    status_message = Str("")
    available_shared = List(str)
    # PodmanRunner stored as Value so Atom allows non-member attributes
    _runner = Value()

    def __init__(self, instances_dir: Path, runner: PodmanRunner | None = None) -> None:
        super().__init__()
        self.instances_dir = str(instances_dir)
        self._runner = runner or PodmanRunner()
        self.refresh()

    # ── observers ─────────────────────────────────────────────────────────────

    def _observe_selected_instance(self, change: dict) -> None:
        """Keep self.selected in sync when selected_instance changes."""
        name = change["value"]
        self.selected = next((i for i in self.instances if i.name == name), None)
        if self.selected:
            self.init_shared_entries(self.selected)

    def _observe_instances(self, change: dict) -> None:
        """Re-resolve selected after the instance list is refreshed."""
        self.selected = next((i for i in self.instances if i.name == self.selected_instance), None)
        if self.selected:
            self.init_shared_entries(self.selected)

    # ── actions ───────────────────────────────────────────────────────────────

    def init_shared_entries(self, model: InstanceModel) -> None:
        """Build SharedVolumeEntry list from available shared + instance config."""
        config_shared: dict[str, str] = {}
        for entry in model.shared:
            try:
                name, mode = parse_shared_entry(entry)
            except Exception:
                name, mode = entry, "rw"
            config_shared[name] = mode

        entries = []
        for name in self.available_shared:
            enabled = name in config_shared
            mode = config_shared.get(name, "rw")
            entries.append(SharedVolumeEntry(name=name, enabled=enabled, mode=mode))
        model.shared_entries = entries

    def refresh(self) -> None:
        """Reload all instances from disk."""
        instances_dir = Path(self.instances_dir)
        try:
            infos = list_all(instances_dir, self._runner)
            self.available_shared = [v.name for v in list_shared(instances_dir)]
            self.instances = [InstanceModel.from_info(i) for i in infos]
            self.status_message = f"Loaded {len(self.instances)} instance(s)"
        except Exception as e:
            self.status_message = f"Error loading instances: {e}"

    # ── actions ──────────────────────────────────────────────────────────────

    def enter_instance(self, name: str, *, root: bool = False) -> None:
        """Open a terminal running scratch-monkey enter for the named instance."""
        cmd = ["scratch-monkey", "enter", name]
        if root:
            cmd.append("--root")
        err = _launch_in_terminal(cmd)
        if err:
            self.status_message = err
        else:
            self.status_message = f"Opened terminal for {name!r}" + (" (root)" if root else "")

    def build_instance(self, name: str) -> None:
        """Open a terminal running scratch-monkey build-instance."""
        err = _launch_in_terminal(["scratch-monkey", "build-instance", name])
        if err:
            self.status_message = err
        else:
            self.status_message = f"Building {name!r} in terminal..."

    def reset_overlay(self, name: str) -> None:
        """Remove the overlay container for the named instance."""
        try:
            result = subprocess.run(
                ["scratch-monkey", "reset", name, "--yes"],
                capture_output=True,
                text=True,
            )
            msg = result.stdout.strip() or result.stderr.strip()
            self.status_message = msg or f"Reset overlay for {name!r}"
        except Exception as e:
            self.status_message = f"Error: {e}"
        self.refresh()

    def delete_instance(self, name: str) -> None:
        """Delete the named instance (no confirmation — caller must confirm)."""
        try:
            result = subprocess.run(
                ["scratch-monkey", "delete", name, "--yes"],
                capture_output=True,
                text=True,
            )
            msg = result.stdout.strip() or result.stderr.strip()
            self.status_message = msg or f"Deleted {name!r}"
            if result.returncode == 0:
                self.selected_instance = ""
        except Exception as e:
            self.status_message = f"Error: {e}"
        self.refresh()

    def new_instance_model(self) -> InstanceModel:
        """Create a fresh InstanceModel with shared entries initialized."""
        m = InstanceModel()
        self.init_shared_entries(m)
        return m

    def create_shared_volume(self, name: str) -> str:
        """Create a new shared volume. Returns '' on success or error string."""
        from ..config import validate_name
        from ..shared import SharedError, create_shared

        try:
            validate_name(name)
            create_shared(name, Path(self.instances_dir))
        except (SharedError, ConfigError) as e:
            return str(e)
        self.refresh()
        self.status_message = f"Created shared volume {name!r}"
        return ""

    def create_instance(
        self, name: str, *, fedora: bool = False, skel: bool = False, config: InstanceConfig | None = None
    ) -> str:
        """Create a new instance. Returns '' on success or error string on failure."""
        base_image = _FEDORA_IMAGE if fedora else _DEFAULT_BASE_IMAGE
        try:
            inst = create(name, Path(self.instances_dir), base_image, _PROJECT_DIR)
        except (InstanceError, ConfigError) as e:
            return str(e)
        if skel:
            skel_copy(inst)
        if config is not None:
            config_path = inst.directory / "scratch.toml"
            save(config_path, config)
        self.refresh()
        self.selected_instance = name
        self.status_message = f"Created instance {name!r}"
        return ""
