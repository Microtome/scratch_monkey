"""Overlay container management for scratch-monkey instances."""

from __future__ import annotations

import logging
import os
import sys

from .config import generate_overlay_id, save
from .container import PodmanError, PodmanRunner
from .instance import Instance, is_fedora_based
from .run_args import build_run_args

logger = logging.getLogger(__name__)


class OverlayError(Exception):
    """Raised for overlay container operation errors."""


def _ensure_overlay_id(instance: Instance) -> str:
    if not instance.config.overlay_id:
        instance.config.overlay_id = generate_overlay_id()
        save(instance.directory / "scratch.toml", instance.config)
    return instance.config.overlay_id


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
    container_name = _ensure_overlay_id(instance)

    if not runner.container_exists(container_name):
        run_args, warnings = build_run_args(instance)
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)
        runner.run_daemon(container_name, image, run_args)

        # User setup is only needed for fedora-based instances.
        # Scratch instances mount /etc from the host read-only — the user
        # already exists on the host and sudo works via host config.
        if is_fedora_based(instance.directory):
            _setup_fedora_user(container_name, runner, sudo=instance.config.sudo)

    elif not runner.container_running(container_name):
        runner.start(container_name)

    return container_name


def _setup_fedora_user(container_name: str, runner: PodmanRunner, *, sudo: bool = True) -> None:
    """Create the host user in a fedora overlay container.

    If sudo=True (default), also installs the sudo package and grants
    passwordless sudo to the user. If sudo=False, only useradd is run —
    the sudo package is not installed and no sudoers entry is written.
    """
    username = os.environ.get("USER", "user")
    uid = os.getuid()

    if sudo:
        # Install sudo if missing
        try:
            runner.exec_capture(
                container_name,
                ["bash", "-c", "rpm -q sudo &>/dev/null || dnf install -y sudo"],
                user="root",
            )
        except PodmanError as exc:
            logger.debug("sudo install skipped: %s", exc)

    # Create user (ignore error if already exists)
    try:
        runner.exec_capture(
            container_name,
            ["useradd", "-u", str(uid), "-M", "-s", "/bin/bash", username],
            user="root",
        )
    except PodmanError as exc:
        logger.debug("useradd skipped (user may exist): %s", exc)

    if sudo:
        # Grant passwordless sudo — use tee to avoid shell interpolation of username
        sudoers_line = f"{username} ALL=(ALL) NOPASSWD: ALL\n"
        runner.exec_capture(
            container_name,
            ["tee", f"/etc/sudoers.d/{username}"],
            user="root",
            input=sudoers_line,
        )
        runner.exec_capture(
            container_name,
            ["chmod", "440", f"/etc/sudoers.d/{username}"],
            user="root",
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
        # Ensure /root exists — scratch images don't create it, and podman
        # exec --workdir /root fails with "No such file or directory".
        # Idempotent (harmless on fedora where /root already exists).
        runner.exec_capture(
            container_name, ["mkdir", "-p", "/root"], user="root",
        )
        options = [
            "--user", "root",
            "--workdir", "/root",
            "-e", "HOME=/root",
            "-e", "USER=root",
            "-e", f"SCRATCH_INSTANCE={instance.name}",
        ]
    else:
        options = [
            "--user", user,
            "--workdir", container_home,
            "-e", f"HOME={container_home}",
            "-e", f"USER={user}",
            "-e", f"SCRATCH_INSTANCE={instance.name}",
        ]

    # Forward display/session env vars so graphical apps work inside the
    # overlay.  The sockets are already bind-mounted at container creation
    # time (via build_run_args), but the env vars must be set on each exec
    # to reflect the current host state (DISPLAY can change between sessions).
    cfg = instance.config
    if cfg.wayland:
        uid = os.getuid()
        options += ["-e", "WAYLAND_DISPLAY=wayland-0", "-e", f"XDG_RUNTIME_DIR=/run/user/{uid}"]
    if cfg.x11:
        display = os.environ.get("DISPLAY", "")
        if display:
            options += ["-e", f"DISPLAY={display}"]
            xauth_file = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
            if os.path.exists(xauth_file):
                options += ["-e", "XAUTHORITY=/tmp/.container-Xauthority"]
    if cfg.ssh:
        ssh_sock = os.environ.get("SSH_AUTH_SOCK", "")
        if ssh_sock and os.path.exists(ssh_sock):
            options += ["-e", f"SSH_AUTH_SOCK={ssh_sock}"]

    runner.exec_interactive(container_name, [cmd], options=options)


def reset(instance: Instance, runner: PodmanRunner) -> bool:
    """Remove the overlay container for an instance.

    Returns True if a container was removed, False if none existed.
    """
    container_name = _ensure_overlay_id(instance)
    if not runner.container_exists(container_name):
        return False
    runner.remove(container_name, force=True)
    return True
