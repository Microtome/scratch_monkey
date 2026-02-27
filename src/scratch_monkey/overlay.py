"""Overlay container management for scratch-monkey instances."""

from __future__ import annotations

import os
import sys

from .container import PodmanError, PodmanRunner
from .instance import Instance, is_fedora_based
from .shared import parse_shared_entry


class OverlayError(Exception):
    """Raised for overlay container operation errors."""


def _gpu_devices() -> list[str]:
    """Detect available GPU device paths."""
    devices = []
    if os.path.exists("/dev/dri"):
        devices.append("/dev/dri")
    if os.path.exists("/dev/kfd"):
        devices.append("/dev/kfd")
    # NVIDIA devices
    for name in ("nvidia0", "nvidiactl", "nvidia-modeset", "nvidia-uvm", "nvidia-uvm-tools"):
        path = f"/dev/{name}"
        if os.path.exists(path):
            devices.append(path)
    return devices


def _overlay_name(instance: Instance) -> str:
    return f"{instance.name}-overlay"


def _build_run_args(instance: Instance) -> list[str]:
    """Build the podman run arguments for an overlay container."""
    cfg = instance.config
    container_home = f"/home/{os.environ.get('USER', 'user')}"

    args = [
        "--security-opt", "label=disable",
        "--network", "host",
        "--hostname", f"{instance.name}.{_short_hostname()}",
        "-e", f"HOME={container_home}",
        "-e", f"USER={os.environ.get('USER', 'user')}",
        "-e", f"SCRATCH_INSTANCE={instance.name}",
        "-v", f"{instance.home_dir}:{container_home}",
    ]

    # Host system mounts for scratch-based (non-fedora) instances
    if not is_fedora_based(instance.directory):
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

    # SSH
    if cfg.ssh:
        ssh_sock = os.environ.get("SSH_AUTH_SOCK", "")
        if ssh_sock and os.path.exists(ssh_sock):
            args += [
                "-v", f"{ssh_sock}:{ssh_sock}",
                "-e", f"SSH_AUTH_SOCK={ssh_sock}",
            ]

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
            print(
                f"Warning: shared volume {shared_name!r} not found, skipping.",
                file=sys.stderr,
            )

    # Extra env vars
    for var in cfg.env:
        args += ["-e", var]

    # GPU passthrough
    if cfg.gpu:
        for dev in _gpu_devices():
            args += ["--device", dev]

    # Extra devices
    for dev in cfg.devices:
        args += ["--device", dev]

    return args


def _short_hostname() -> str:
    import socket
    return socket.gethostname().split(".")[0]


def ensure_running(
    instance: Instance,
    runner: PodmanRunner,
    image: str,
) -> str:
    """Ensure the overlay container for the instance is running.

    Creates it if missing, starts it if stopped.
    Returns the container name.

    For fedora-based instances, creates the host user and grants sudo.
    For scratch-based instances, skips user setup entirely.
    """
    container_name = _overlay_name(instance)

    if not runner.container_exists(container_name):
        run_args = _build_run_args(instance)
        runner.run_daemon(container_name, image, run_args)

        # User setup is only needed for fedora-based instances.
        # Scratch instances mount /etc from the host read-only — the user
        # already exists on the host and sudo works via host config.
        if is_fedora_based(instance.directory):
            _setup_fedora_user(container_name, runner)

    elif not runner.container_running(container_name):
        runner.start(container_name)

    return container_name


def _setup_fedora_user(container_name: str, runner: PodmanRunner) -> None:
    """Install sudo and create the host user with passwordless sudo access."""
    username = os.environ.get("USER", "user")
    uid = os.getuid()

    # Install sudo if missing
    try:
        runner.exec_capture(
            container_name,
            ["bash", "-c", "rpm -q sudo &>/dev/null || dnf install -y sudo"],
        )
    except PodmanError:
        pass  # best-effort

    # Create user (ignore error if already exists)
    try:
        runner.exec_capture(
            container_name,
            ["useradd", "-u", str(uid), "-M", "-s", "/bin/bash", username],
        )
    except PodmanError:
        pass  # user may already exist

    # Ensure home directory is owned by the user
    container_home = f"/home/{username}"
    try:
        runner.exec_capture(
            container_name,
            ["chown", f"{uid}:{uid}", container_home],
        )
    except PodmanError:
        pass  # best-effort

    # Grant passwordless sudo
    sudoers_line = f"{username} ALL=(ALL) NOPASSWD: ALL"
    runner.exec_capture(
        container_name,
        [
            "bash", "-c",
            f"echo '{sudoers_line}' > /etc/sudoers.d/{username} "
            f"&& chmod 440 /etc/sudoers.d/{username}",
        ],
    )


def exec_shell(
    instance: Instance,
    runner: PodmanRunner,
    container_name: str,
    *,
    root: bool = False,
    cmd: str = "/bin/bash",
) -> None:
    """Exec an interactive shell in the overlay container.

    If root=True, runs as root with /root as workdir.
    Otherwise runs as the current user with the instance home as workdir.
    """
    user = os.environ.get("USER", "user")
    container_home = f"/home/{user}"

    if root:
        exec_args = [
            "-it",
            "--workdir", "/root",
            "-e", "HOME=/root",
            "-e", "USER=root",
            "-e", f"SCRATCH_INSTANCE={instance.name}",
            container_name,
            cmd,
        ]
    else:
        exec_args = [
            "-it",
            "--user", user,
            "--workdir", container_home,
            "-e", f"HOME={container_home}",
            "-e", f"USER={user}",
            "-e", f"SCRATCH_INSTANCE={instance.name}",
            container_name,
            cmd,
        ]

    runner._run(["exec", *exec_args], capture=False)


def reset(instance: Instance, runner: PodmanRunner) -> bool:
    """Remove the overlay container for an instance.

    Returns True if a container was removed, False if none existed.
    """
    container_name = _overlay_name(instance)
    if not runner.container_exists(container_name):
        return False
    runner.remove(container_name, force=True)
    return True
