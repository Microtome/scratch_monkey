"""scratch-monkey CLI — all user-facing commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from ..config import ConfigError
from ..container import PodmanError, PodmanRunner
from ..export import ExportError, export_command, unexport
from ..instance import (
    Instance,
    InstanceError,
    clone,
    create,
    delete,
    detect_base_image,
    is_fedora_based,
    list_all,
    skel_copy,
)
from ..overlay import ensure_running, exec_shell
from ..overlay import reset as overlay_reset
from ..shared import (
    SharedError,
    add_to_instance,
    create_shared,
    delete_shared,
    list_shared,
    parse_shared_entry,
    remove_from_instance,
)

DEFAULT_INSTANCES_DIR = Path.home() / "scratch-monkey"
DEFAULT_BASE_IMAGE = "scratch_dev"
FEDORA_IMAGE = "scratch_dev_fedora"

# Path to this package's project directory (where Dockerfiles live)
_PROJECT_DIR = Path(__file__).parent.parent.parent.parent


@click.group()
@click.option(
    "--instances-dir",
    envvar="SCRATCH_MONKEY_INSTANCES_DIR",
    default=str(DEFAULT_INSTANCES_DIR),
    show_default=True,
    help="Directory where instances are stored.",
)
@click.option(
    "--base-image",
    default=DEFAULT_BASE_IMAGE,
    show_default=True,
    help="Default base image for new instances.",
)
@click.pass_context
def cli(ctx: click.Context, instances_dir: str, base_image: str) -> None:
    """scratch-monkey: Podman-based dev container manager."""
    ctx.ensure_object(dict)
    ctx.obj["instances_dir"] = Path(instances_dir)
    ctx.obj["base_image"] = base_image
    ctx.obj["runner"] = PodmanRunner()


def _get_instance(instances_dir: Path, name: str) -> Instance:
    """Load an instance by name or exit with an error."""
    inst_dir = instances_dir / name
    if not inst_dir.is_dir():
        click.echo(f"Error: instance {name!r} not found at {inst_dir}", err=True)
        sys.exit(1)
    return Instance.from_directory(inst_dir)


# ─── Instance management ──────────────────────────────────────────────────────


@cli.command(name="create")
@click.argument("name")
@click.option("--fedora", is_flag=True, default=False, help="Use fedora base image.")
@click.option("--skel", is_flag=True, default=False, help="Copy /etc/skel into home.")
@click.pass_context
def create_cmd(ctx: click.Context, name: str, fedora: bool, skel: bool) -> None:
    """Create a new instance."""
    instances_dir: Path = ctx.obj["instances_dir"]
    base_image = FEDORA_IMAGE if fedora else ctx.obj["base_image"]
    try:
        inst = create(name, instances_dir, base_image, _PROJECT_DIR)
    except (InstanceError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Created instance {name!r} at {inst.directory} (base: {base_image})")
    if skel:
        copied = skel_copy(inst)
        if copied:
            click.echo(f"Copied {len(copied)} file(s) from /etc/skel: {', '.join(copied)}")
        else:
            click.echo("No files copied from /etc/skel.")
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"  Edit config:      scratch-monkey edit {name}")
    click.echo(f"  Edit Dockerfile:  scratch-monkey edit {name} --file dockerfile")
    click.echo(f"  Run:              scratch-monkey enter {name}")


@cli.command(name="clone")
@click.argument("source")
@click.argument("dest")
@click.pass_context
def clone_cmd(ctx: click.Context, source: str, dest: str) -> None:
    """Clone an existing instance (fresh home directory)."""
    instances_dir: Path = ctx.obj["instances_dir"]
    try:
        clone(source, dest, instances_dir)
    except (InstanceError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Cloned {source!r} → {dest!r} (fresh home directory)")


@cli.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def delete_cmd(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete an instance (removes directory + image)."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]

    inst_dir = instances_dir / name
    if not inst_dir.is_dir():
        click.echo(f"Error: instance {name!r} not found at {inst_dir}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(
            f"Delete instance {name!r} and all its data?", abort=True
        )

    try:
        delete(name, instances_dir, runner)
    except (InstanceError, PodmanError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Deleted instance {name!r}")


@cli.command(name="list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List all instances."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]

    instances = list_all(instances_dir, runner)
    if not instances:
        click.echo("No instances found. Create one with: scratch-monkey create <name>")
        return

    click.echo(f"{'INSTANCE':<20} {'IMAGE':<8} {'OVERLAY':<10} {'DIRECTORY':<40} CONFIG")
    for info in instances:
        built = "yes" if info.image_built else "no"
        overlay = "running" if info.overlay_running else "stopped"
        cfg = info.config
        active_parts = []
        if cfg.wayland:
            active_parts.append("wayland=true")
        if cfg.ssh:
            active_parts.append("ssh=true")
        if cfg.overlay:
            active_parts.append("overlay=true")
        if cfg.shared:
            active_parts.append(f"shared={cfg.shared}")
        config_str = ", ".join(active_parts) if active_parts else "(defaults)"
        click.echo(
            f"{info.name:<20} {built:<8} {overlay:<10} {str(info.directory):<40} {config_str}"
        )


@cli.command()
@click.argument("name")
@click.pass_context
def skel(ctx: click.Context, name: str) -> None:
    """Copy /etc/skel bash config files into instance home."""
    instances_dir: Path = ctx.obj["instances_dir"]
    inst = _get_instance(instances_dir, name)
    copied = skel_copy(inst)
    if copied:
        click.echo(f"Copied {len(copied)} file(s): {', '.join(copied)}")
    else:
        click.echo("No new files copied (all already exist or /etc/skel is empty).")


@cli.command()
@click.argument("name")
@click.option(
    "--file", "-f",
    type=click.Choice(["config", "dockerfile", "env"]),
    default="config",
    show_default=True,
    help="Which file to edit.",
)
@click.pass_context
def edit(ctx: click.Context, name: str, file: str) -> None:
    """Edit an instance file (config, dockerfile, or env)."""
    instances_dir: Path = ctx.obj["instances_dir"]
    inst_dir = instances_dir / name
    if not inst_dir.is_dir():
        click.echo(f"Error: instance {name!r} not found", err=True)
        sys.exit(1)

    file_map = {
        "config": inst_dir / "scratch.toml",
        "dockerfile": inst_dir / "Dockerfile",
        "env": inst_dir / ".env",
    }
    target = file_map[file]
    editor = os.environ.get("EDITOR", "vi")
    os.execvp(editor, [editor, str(target)])


# ─── Build ────────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--fedora", is_flag=True, default=False, help="Build the fedora base image.")
@click.option("--yes", "-y", is_flag=True, help="Rebuild without confirmation if image exists.")
@click.pass_context
def build(ctx: click.Context, fedora: bool, yes: bool) -> None:
    """Build a base image."""
    runner: PodmanRunner = ctx.obj["runner"]
    base_image = FEDORA_IMAGE if fedora else ctx.obj["base_image"]

    if runner.image_exists(base_image):
        if not yes:
            click.confirm(f"Image {base_image!r} already exists. Rebuild?", abort=True)

    if fedora:
        dockerfile = str(_PROJECT_DIR / "Dockerfile.fedora")
        runner.build(base_image, str(_PROJECT_DIR), dockerfile=dockerfile)
    else:
        runner.build(base_image, str(_PROJECT_DIR))
    click.echo(f"Built image {base_image!r}")


@cli.command(name="build-instance")
@click.argument("name")
@click.pass_context
def build_instance(ctx: click.Context, name: str) -> None:
    """Build an instance's Dockerfile (tagged as the instance name)."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]
    inst = _get_instance(instances_dir, name)

    # Detect base from Dockerfile
    instance_base = detect_base_image(inst.directory) or ctx.obj["base_image"]

    # Auto-build base if missing
    if not runner.image_exists(instance_base):
        click.echo(f"Base image {instance_base!r} not found, building...")
        if "fedora" in instance_base:
            runner.build(instance_base, str(_PROJECT_DIR), dockerfile=str(_PROJECT_DIR / "Dockerfile.fedora"))
        else:
            runner.build(instance_base, str(_PROJECT_DIR))

    runner.build(name, str(inst.directory), dockerfile=str(inst.directory / "Dockerfile"))
    click.echo(f"Built instance image {name!r}")


# ─── Run / Enter ──────────────────────────────────────────────────────────────


@cli.command()
@click.argument("name")
@click.option("--root", is_flag=True, default=False, help="Run as root.")
@click.option("--wayland", is_flag=True, default=False, help="Enable Wayland socket sharing.")
@click.option("--ssh", is_flag=True, default=False, help="Enable SSH agent sharing.")
@click.option("--cmd", default="", help="Override the command to run.")
@click.pass_context
def run(
    ctx: click.Context,
    name: str,
    root: bool,
    wayland: bool,
    ssh: bool,
    cmd: str,
) -> None:
    """Run a scratch-monkey instance."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]
    inst = _get_instance(instances_dir, name)
    cfg = inst.config

    # CLI overrides
    if wayland:
        cfg.wayland = True
    if ssh:
        cfg.ssh = True
    if cmd:
        cfg.cmd = cmd

    _run_instance(inst, runner, ctx.obj["base_image"], root=root)


@cli.command()
@click.argument("name")
@click.option("--root", is_flag=True, default=False, help="Enter as root.")
@click.pass_context
def enter(ctx: click.Context, name: str, root: bool) -> None:
    """Drop into an interactive shell in an instance."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]
    inst = _get_instance(instances_dir, name)
    _run_instance(inst, runner, ctx.obj["base_image"], root=root)


@cli.command()
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def reset(ctx: click.Context, name: str, yes: bool) -> None:
    """Reset overlay container for an instance."""
    instances_dir: Path = ctx.obj["instances_dir"]
    runner: PodmanRunner = ctx.obj["runner"]
    inst = _get_instance(instances_dir, name)

    if not runner.container_exists(f"{name}-overlay"):
        click.echo(f"No overlay container found for {name!r}")
        return

    if not yes:
        click.confirm(
            f"Remove overlay container for {name!r}? Package installs will be lost.",
            abort=True,
        )

    removed = overlay_reset(inst, runner)
    if removed:
        click.echo(f"Overlay container for {name!r} removed.")


def _run_instance(
    inst: Instance,
    runner: PodmanRunner,
    default_base: str,
    *,
    root: bool = False,
) -> None:
    """Assemble podman args and launch the container."""
    cfg = inst.config
    user = os.environ.get("USER", "user")

    # Determine image
    if runner.image_exists(inst.name):
        run_image = inst.name
    else:
        instance_base = detect_base_image(inst.directory) or default_base
        run_image = instance_base
        if not runner.image_exists(run_image):
            click.echo(f"Base image {run_image!r} not found, building...")
            if "fedora" in run_image:
                runner.build(run_image, str(_PROJECT_DIR), dockerfile=str(_PROJECT_DIR / "Dockerfile.fedora"))
            else:
                runner.build(run_image, str(_PROJECT_DIR))

    fedora = is_fedora_based(inst.directory)

    # Ensure home dir exists
    if not inst.home_dir.exists():
        click.confirm(f"{inst.home_dir} does not exist. Create it?", abort=True)
        inst.home_dir.mkdir(parents=True)

    # Overlay mode
    if cfg.overlay:
        container_name = ensure_running(inst, runner, run_image)
        exec_shell(inst, runner, container_name, root=root, cmd=cfg.cmd)
        return

    # Container home path
    if root and not cfg.overlay:
        container_home = "/root"
    else:
        container_home = f"/home/{user}"

    podman_args = [
        "--rm", "-it",
        "--security-opt", "label=disable",
        "--network=host",
        "--hostname", f"{inst.name}.{_short_hostname()}",
        "-e", f"HOME={container_home}",
        "-e", f"USER={user}",
        "-e", f"SCRATCH_INSTANCE={inst.name}",
        "-v", f"{inst.home_dir}:{container_home}",
        "--workdir", container_home,
    ]

    if not root:
        podman_args.append("--userns=keep-id")

    # Host mounts for scratch
    if not fedora:
        podman_args += [
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
            podman_args += [
                "-v", f"{wayland_sock}:{wayland_sock}",
                "-e", "WAYLAND_DISPLAY=wayland-0",
                "-e", f"XDG_RUNTIME_DIR=/run/user/{uid}",
            ]
        else:
            click.echo(f"Warning: Wayland socket not found at {wayland_sock}, skipping.", err=True)

    # SSH
    if cfg.ssh:
        ssh_sock = os.environ.get("SSH_AUTH_SOCK", "")
        if ssh_sock and os.path.exists(ssh_sock):
            podman_args += [
                "-v", f"{ssh_sock}:{ssh_sock}",
                "-e", f"SSH_AUTH_SOCK={ssh_sock}",
            ]
        else:
            click.echo("Warning: SSH_AUTH_SOCK not set or socket missing, skipping.", err=True)

    # .env file
    env_file = inst.directory / ".env"
    if env_file.exists():
        podman_args += ["--env-file", str(env_file)]

    # Extra volumes
    for vol in cfg.volumes:
        podman_args += ["-v", vol]

    # Shared volumes
    instances_dir = inst.directory.parent
    for shared_entry in cfg.shared:
        shared_name, mode = parse_shared_entry(shared_entry)
        shared_path = instances_dir / ".shared" / shared_name
        if shared_path.is_dir():
            mount_spec = f"{shared_path}:/shared/{shared_name}"
            if mode == "ro":
                mount_spec += ":ro"
            podman_args += ["-v", mount_spec]
        else:
            click.echo(
                f"Warning: shared volume {shared_name!r} not found, skipping.",
                err=True,
            )

    # Extra env vars
    for var in cfg.env:
        podman_args += ["-e", var]

    podman_args.append(run_image)
    podman_args.append(cfg.cmd)

    runner.run(podman_args)


def _short_hostname() -> str:
    import socket
    return socket.gethostname().split(".")[0]


# ─── Export ───────────────────────────────────────────────────────────────────


@cli.command(name="export")
@click.argument("name")
@click.argument("cmd")
@click.argument("bin", default="")
@click.pass_context
def export_cmd(ctx: click.Context, name: str, cmd: str, bin: str) -> None:
    """Export a command from an instance to ~/.local/bin."""
    instances_dir: Path = ctx.obj["instances_dir"]
    base_image: str = ctx.obj["base_image"]
    inst = _get_instance(instances_dir, name)
    out = export_command(inst, cmd, bin_name=bin, base_image=base_image)
    click.echo(f"Exported {cmd!r} from {name!r} → {out}")


@cli.command(name="unexport")
@click.argument("bin")
def unexport_cmd(bin: str) -> None:
    """Remove an exported command from ~/.local/bin."""
    try:
        unexport(bin)
    except ExportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Removed ~/.local/bin/{bin}")


# ─── GUI ──────────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def gui(ctx: click.Context) -> None:
    """Launch the scratch-monkey GUI."""
    try:
        from ..gui.main import main as gui_main
    except ImportError:
        click.echo(
            "Error: GUI dependencies not installed.\n"
            "Install with: uv tool install --editable '.[gui]'",
            err=True,
        )
        sys.exit(1)
    gui_main(instances_dir=ctx.obj["instances_dir"])


# ─── Shared volumes ───────────────────────────────────────────────────────────


@cli.group()
def share() -> None:
    """Manage shared volumes."""


@share.command(name="create")
@click.argument("name")
@click.pass_context
def share_create(ctx: click.Context, name: str) -> None:
    """Create a shared volume."""
    instances_dir: Path = ctx.obj["instances_dir"]
    try:
        path = create_shared(name, instances_dir)
    except SharedError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Created shared volume {name!r} at {path}")


@share.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@click.pass_context
def share_delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a shared volume (removes config references)."""
    instances_dir: Path = ctx.obj["instances_dir"]
    if not yes:
        click.confirm(f"Delete shared volume {name!r} and all its data?", abort=True)
    try:
        delete_shared(name, instances_dir)
    except SharedError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Deleted shared volume {name!r}")


@share.command(name="add")
@click.argument("volume")
@click.argument("instance")
@click.pass_context
def share_add(ctx: click.Context, volume: str, instance: str) -> None:
    """Add a shared volume to an instance's config."""
    instances_dir: Path = ctx.obj["instances_dir"]
    inst = _get_instance(instances_dir, instance)
    try:
        add_to_instance(volume, inst, instances_dir)
    except SharedError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Added shared volume {volume!r} to instance {instance!r}")


@share.command(name="remove")
@click.argument("volume")
@click.argument("instance")
@click.pass_context
def share_remove(ctx: click.Context, volume: str, instance: str) -> None:
    """Remove a shared volume from an instance's config."""
    instances_dir: Path = ctx.obj["instances_dir"]
    inst = _get_instance(instances_dir, instance)
    removed = remove_from_instance(volume, inst)
    if removed:
        click.echo(f"Removed shared volume {volume!r} from instance {instance!r}")
    else:
        click.echo(f"Shared volume {volume!r} not in {instance!r}'s config")


@share.command(name="list")
@click.pass_context
def share_list(ctx: click.Context) -> None:
    """List all shared volumes and which instances use them."""
    instances_dir: Path = ctx.obj["instances_dir"]
    volumes = list_shared(instances_dir)
    if not volumes:
        click.echo("No shared volumes found.")
        return
    click.echo(f"{'VOLUME':<20} USED BY")
    for vol in volumes:
        users = ", ".join(vol.used_by) if vol.used_by else "(none)"
        click.echo(f"{vol.name:<20} {users}")
