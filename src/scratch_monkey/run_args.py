"""Shared run arguments, constants, and helpers for scratch-monkey."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from .instance import Instance, is_fedora_based
from .shared import parse_shared_entry

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_BASE_IMAGE = "scratch_dev"
FEDORA_IMAGE = "scratch_dev_fedora"

# Path to this package's project directory (where Dockerfiles live)
PROJECT_DIR = Path(__file__).parent.parent.parent


def short_hostname() -> str:
    """Return the short (non-FQDN) hostname."""
    return socket.gethostname().split(".")[0]


def gpu_devices() -> list[str]:
    """Detect available GPU device paths."""
    devices = []
    if os.path.exists("/dev/dri"):
        devices.append("/dev/dri")
    if os.path.exists("/dev/kfd"):
        devices.append("/dev/kfd")
    for name in ("nvidia0", "nvidiactl", "nvidia-modeset", "nvidia-uvm", "nvidia-uvm-tools"):
        path = f"/dev/{name}"
        if os.path.exists(path):
            devices.append(path)
    return devices


def build_run_args(
    instance: Instance,
    *,
    is_fedora: bool | None = None,
    root: bool = False,
) -> tuple[list[str], list[str]]:
    """Build the podman run arguments for a container.

    Shared between overlay mode (overlay.py) and direct-run mode (cli/main.py).
    Returns (args, warnings) where warnings is a list of human-readable messages.
    """
    cfg = instance.config
    user = os.environ.get("USER", "user")
    warnings: list[str] = []

    if root:
        container_home = "/root"
    else:
        container_home = f"/home/{user}"

    if is_fedora is None:
        is_fedora = is_fedora_based(instance.directory)

    args = [
        "--security-opt", "label=disable",
        "--network", "host",
        "--hostname", f"{instance.name}.{short_hostname()}",
        "-e", f"HOME={container_home}",
        "-e", f"USER={user}",
        "-e", f"SCRATCH_INSTANCE={instance.name}",
        "-v", f"{instance.home_dir}:{container_home}",
    ]

    if not root:
        args.append("--userns=keep-id")

    # Host system mounts for scratch-based (non-fedora) instances
    if not is_fedora:
        args += [
            "-v", "/usr:/usr:ro",
            "-v", "/etc:/etc:ro",
            "-v", "/var/usrlocal:/var/usrlocal:ro",
            "-v", "/var/opt:/var/opt:ro",
            "-v", "/var/usrlocal:/usr/local:ro",
        ]

    # Wayland
    if cfg.wayland:
        uid = os.getuid()
        wayland_sock = f"/run/user/{uid}/wayland-0"
        if os.path.exists(wayland_sock):
            args += [
                "-v", f"{wayland_sock}:{wayland_sock}",
                "-e", "WAYLAND_DISPLAY=wayland-0",
                "-e", f"XDG_RUNTIME_DIR=/run/user/{uid}",
            ]
        else:
            warnings.append(f"Wayland socket not found at {wayland_sock}, skipping.")

    # SSH
    if cfg.ssh:
        ssh_sock = os.environ.get("SSH_AUTH_SOCK", "")
        if ssh_sock and os.path.exists(ssh_sock):
            args += [
                "-v", f"{ssh_sock}:{ssh_sock}",
                "-e", f"SSH_AUTH_SOCK={ssh_sock}",
            ]
        else:
            warnings.append("SSH_AUTH_SOCK not set or socket missing, skipping.")

    # .env file
    env_file = instance.directory / ".env"
    if env_file.exists():
        args += ["--env-file", str(env_file)]

    # Extra volumes
    for vol in cfg.volumes:
        args += ["-v", vol]

    # Shared volumes
    instances_dir = instance.directory.parent
    for shared_entry in cfg.shared:
        shared_name, mode = parse_shared_entry(shared_entry)
        shared_path = instances_dir / ".shared" / shared_name
        if shared_path.is_dir():
            mount_spec = f"{shared_path}:/shared/{shared_name}"
            if mode == "ro":
                mount_spec += ":ro"
            args += ["-v", mount_spec]
        else:
            warnings.append(f"Shared volume {shared_name!r} not found, skipping.")

    # Extra env vars
    for var in cfg.env:
        args += ["-e", var]

    # GPU passthrough
    if cfg.gpu:
        for dev in gpu_devices():
            args += ["--device", dev]

    # Extra devices
    for dev in cfg.devices:
        args += ["--device", dev]

    return args, warnings
