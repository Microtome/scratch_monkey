"""Tests for scratch_monkey.run_args module."""

import os
from unittest.mock import patch

from scratch_monkey.overlay import ensure_running
from scratch_monkey.run_args import build_run_args, gpu_devices

# Save references to real os.path functions before any patching
_real_isdir = os.path.isdir
_real_exists = os.path.exists
_real_expanduser = os.path.expanduser

# ─── gpu_devices ─────────────────────────────────────────────────────────────


class TestGpuDevices:
    def test_detects_dri(self, tmp_path):
        with patch("os.path.exists", side_effect=lambda p: p == "/dev/dri"):
            devices = gpu_devices()
        assert "/dev/dri" in devices

    def test_detects_kfd(self, tmp_path):
        with patch("os.path.exists", side_effect=lambda p: p == "/dev/kfd"):
            devices = gpu_devices()
        assert "/dev/kfd" in devices

    def test_detects_nvidia_devices(self):
        nvidia_devs = {"/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-modeset",
                       "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools"}
        with patch("os.path.exists", side_effect=lambda p: p in nvidia_devs):
            devices = gpu_devices()
        for dev in nvidia_devs:
            assert dev in devices

    def test_empty_when_no_gpu(self):
        with patch("os.path.exists", return_value=False):
            devices = gpu_devices()
        assert devices == []

    def test_detects_multiple(self):
        present = {"/dev/dri", "/dev/kfd", "/dev/nvidia0"}
        with patch("os.path.exists", side_effect=lambda p: p in present):
            devices = gpu_devices()
        assert "/dev/dri" in devices
        assert "/dev/kfd" in devices
        assert "/dev/nvidia0" in devices


# ─── build_run_args userns ───────────────────────────────────────────────────


class TestBuildRunArgsUserns:
    def test_userns_keep_id_in_scratch_args(self, scratch_instance):
        """--userns=keep-id must appear in run args for scratch instances."""
        args, _warnings = build_run_args(scratch_instance)
        assert "--userns=keep-id" in args

    def test_userns_keep_id_in_fedora_args(self, fedora_instance):
        """--userns=keep-id must appear in run args for fedora instances."""
        args, _warnings = build_run_args(fedora_instance)
        assert "--userns=keep-id" in args

    def test_build_run_args_root_excludes_userns(self, scratch_instance):
        """root=True should exclude --userns=keep-id and use /root as HOME."""
        args, _warnings = build_run_args(scratch_instance, root=True)
        assert "--userns=keep-id" not in args
        env_args = [args[i + 1] for i in range(len(args)) if args[i] == "-e" and i + 1 < len(args)]
        assert "HOME=/root" in env_args


# ─── build_run_args gpu + devices ────────────────────────────────────────────


class TestBuildRunArgsGpuAndDevices:
    def test_gpu_flag_adds_detected_devices(self, scratch_instance):
        scratch_instance.config.gpu = True
        with patch("scratch_monkey.run_args.gpu_devices", return_value=["/dev/dri", "/dev/kfd"]):
            args, _warnings = build_run_args(scratch_instance)
        assert "--device" in args
        assert "/dev/dri" in args
        assert "/dev/kfd" in args

    def test_gpu_false_nogpu_devices(self, scratch_instance):
        scratch_instance.config.gpu = False
        with patch("scratch_monkey.run_args.gpu_devices", return_value=["/dev/dri"]):
            args, _warnings = build_run_args(scratch_instance)
        # gpu_devices should not be consulted at all
        assert "/dev/dri" not in args

    def test_extra_devices_added(self, scratch_instance):
        scratch_instance.config.devices = ["/dev/video0", "/dev/bus/usb"]
        args, _warnings = build_run_args(scratch_instance)
        assert "--device" in args
        assert "/dev/video0" in args
        assert "/dev/bus/usb" in args

    def test_no_devices_when_empty(self, scratch_instance):
        scratch_instance.config.gpu = False
        scratch_instance.config.devices = []
        args, _warnings = build_run_args(scratch_instance)
        assert "--device" not in args

    def test_gpu_and_extra_devices_combined(self, scratch_instance):
        scratch_instance.config.gpu = True
        scratch_instance.config.devices = ["/dev/video0"]
        with patch("scratch_monkey.run_args.gpu_devices", return_value=["/dev/dri"]):
            args, _warnings = build_run_args(scratch_instance)
        assert "/dev/dri" in args
        assert "/dev/video0" in args


# ─── build_run_args shared volumes ────────────────────────────────────────────


class TestBuildRunArgsSharedVolumes:
    """Tests for shared volume expansion in build_run_args."""

    def test_shared_volume_rw_mount(self, scratch_instance, mock_runner, tmp_path):
        """Shared volume with default rw mode mounts without :ro suffix."""
        instances_dir = scratch_instance.directory.parent
        shared_dir = instances_dir / ".shared" / "comms"
        shared_dir.mkdir(parents=True)
        scratch_instance.config.shared = ["comms"]

        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_monkey")
        call_args = mock_runner.run_daemon.call_args
        run_args = call_args[0][2]
        mount = f"{shared_dir}:/shared/comms"
        assert mount in run_args

    def test_shared_volume_ro_mount(self, scratch_instance, mock_runner, tmp_path):
        """Shared volume with :ro suffix mounts with :ro."""
        instances_dir = scratch_instance.directory.parent
        shared_dir = instances_dir / ".shared" / "comms"
        shared_dir.mkdir(parents=True)
        scratch_instance.config.shared = ["comms:ro"]

        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_monkey")
        call_args = mock_runner.run_daemon.call_args
        run_args = call_args[0][2]
        mount = f"{shared_dir}:/shared/comms:ro"
        assert mount in run_args

    def test_missing_shared_volume_skipped(self, scratch_instance, mock_runner):
        """Missing shared volume directory is silently skipped."""
        scratch_instance.config.shared = ["nonexistent"]

        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_monkey")
        call_args = mock_runner.run_daemon.call_args
        run_args = call_args[0][2]
        assert not any("nonexistent" in arg for arg in run_args)


# ─── build_run_args features ──────────────────────────────────────────────────


class TestBuildRunArgsFeatures:
    """Tests for build_run_args: wayland, SSH, env vars, hostname, volumes, .env file."""

    def test_hostname_includes_instance_name(self, scratch_instance):
        args, _warnings = build_run_args(scratch_instance)
        hostname_idx = args.index("--hostname")
        hostname = args[hostname_idx + 1]
        assert hostname.startswith("myinstance.")  # uses fixture name

    def test_env_vars_added(self, scratch_instance):
        scratch_instance.config.env = ["FOO=bar", "BAZ=qux"]
        args, _warnings = build_run_args(scratch_instance)
        assert "FOO=bar" in args
        assert "BAZ=qux" in args

    def test_extra_volumes_added(self, scratch_instance):
        scratch_instance.config.volumes = ["/host/path:/container/path"]
        args, _warnings = build_run_args(scratch_instance)
        assert "/host/path:/container/path" in args

    def test_env_file_included_when_exists(self, scratch_instance):
        # .env already exists (created by fixture)
        args, _warnings = build_run_args(scratch_instance)
        assert "--env-file" in args

    def test_env_file_skipped_when_missing(self, scratch_instance):
        env_file = scratch_instance.directory / ".env"
        env_file.unlink()
        args, _warnings = build_run_args(scratch_instance)
        assert "--env-file" not in args

    def test_wayland_warning_when_socket_missing(self, scratch_instance):
        scratch_instance.config.wayland = True
        with patch("os.path.exists", return_value=False):
            args, warnings = build_run_args(scratch_instance)
        assert any("Wayland" in w for w in warnings)
        assert "WAYLAND_DISPLAY=wayland-0" not in args

    def test_ssh_warning_when_sock_missing(self, scratch_instance):
        scratch_instance.config.ssh = True
        with patch.dict(os.environ, {"SSH_AUTH_SOCK": ""}, clear=False):
            args, warnings = build_run_args(scratch_instance)
        assert any("SSH" in w for w in warnings)

    def test_scratch_instance_has_host_mounts(self, scratch_instance):
        args, _warnings = build_run_args(scratch_instance)
        assert "/usr:/usr:ro" in args
        assert "/etc:/etc:ro" in args

    def test_scratch_instance_has_tmpfs(self, scratch_instance):
        """Scratch instances get tmpfs mounts for /tmp and /root."""
        args, _warnings = build_run_args(scratch_instance)
        # Collect all tmpfs targets
        tmpfs_targets = [args[i + 1] for i in range(len(args)) if args[i] == "--tmpfs" and i + 1 < len(args)]
        assert "/tmp" in tmpfs_targets
        assert "/root" in tmpfs_targets

    def test_fedora_instance_no_tmpfs(self, fedora_instance):
        """Fedora instances do not get tmpfs mounts (they have their own)."""
        args, _warnings = build_run_args(fedora_instance)
        assert "--tmpfs" not in args

    def test_fedora_instance_no_host_mounts(self, fedora_instance):
        args, _warnings = build_run_args(fedora_instance)
        assert "/usr:/usr:ro" not in args

    def test_scratch_instance_env(self, scratch_instance):
        """Verify SCRATCH_INSTANCE env var is set."""
        args, _warnings = build_run_args(scratch_instance)
        env_args = [args[i + 1] for i in range(len(args)) if args[i] == "-e" and i + 1 < len(args)]
        assert "SCRATCH_INSTANCE=myinstance" in env_args  # fixture name

    def test_shared_volume_warning_when_missing(self, scratch_instance):
        scratch_instance.config.shared = ["nonexistent"]
        args, warnings = build_run_args(scratch_instance)
        assert any("nonexistent" in w for w in warnings)


# ─── build_run_args X11 ─────────────────────────────────────────────────────


class TestBuildRunArgsX11:
    """Tests for X11 display socket sharing in build_run_args."""

    def test_x11_socket_and_display_detected(self, scratch_instance, tmp_path):
        """X11 mounts DISPLAY, socket dir, and Xauthority when all present."""
        scratch_instance.config.x11 = True
        xauth_path = str(tmp_path / ".Xauthority")

        def mock_isdir(path):
            if path == "/tmp/.X11-unix":
                return True
            return _real_isdir(path)

        def mock_exists(path):
            if str(path) == xauth_path:
                return True
            return _real_exists(path)

        def mock_expanduser(path):
            if path == "~/.Xauthority":
                return xauth_path
            return _real_expanduser(path)

        with (
            patch.dict(os.environ, {"DISPLAY": ":0", "USER": "testuser"}, clear=False),
            patch("scratch_monkey.run_args.os.path.isdir", side_effect=mock_isdir),
            patch("scratch_monkey.run_args.os.path.exists", side_effect=mock_exists),
            patch("scratch_monkey.run_args.os.path.expanduser", side_effect=mock_expanduser),
        ):
            os.environ.pop("XAUTHORITY", None)
            os.environ["DISPLAY"] = ":0"
            args, warnings = build_run_args(scratch_instance, is_fedora=False)

        assert "-v" in args
        assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" in args
        assert "DISPLAY=:0" in args
        assert f"{xauth_path}:/tmp/.container-Xauthority:ro" in args
        assert "XAUTHORITY=/tmp/.container-Xauthority" in args
        assert len(warnings) == 0

    def test_x11_missing_display(self, scratch_instance):
        """Warning when DISPLAY is empty."""
        scratch_instance.config.x11 = True
        with patch.dict(os.environ, {"DISPLAY": ""}, clear=False):
            args, warnings = build_run_args(scratch_instance)
        assert any("x11" in w.lower() for w in warnings)
        assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" not in args

    def test_x11_missing_socket_dir(self, scratch_instance):
        """Warning when X11 socket dir does not exist."""
        scratch_instance.config.x11 = True

        def mock_isdir(path):
            if path == "/tmp/.X11-unix":
                return False
            return _real_isdir(path)

        with (
            patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False),
            patch("scratch_monkey.run_args.os.path.isdir", side_effect=mock_isdir),
        ):
            args, warnings = build_run_args(scratch_instance)
        assert any("x11" in w.lower() for w in warnings)
        assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" not in args

    def test_x11_missing_xauthority(self, scratch_instance, tmp_path):
        """Socket and DISPLAY mounted but no XAUTHORITY when file missing."""
        scratch_instance.config.x11 = True
        xauth_path = str(tmp_path / ".Xauthority-nonexistent")

        def mock_isdir(path):
            if path == "/tmp/.X11-unix":
                return True
            return _real_isdir(path)

        def mock_exists(path):
            if str(path) == xauth_path:
                return False
            return _real_exists(path)

        def mock_expanduser(path):
            if path == "~/.Xauthority":
                return xauth_path
            return _real_expanduser(path)

        with (
            patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False),
            patch("scratch_monkey.run_args.os.path.isdir", side_effect=mock_isdir),
            patch("scratch_monkey.run_args.os.path.exists", side_effect=mock_exists),
            patch("scratch_monkey.run_args.os.path.expanduser", side_effect=mock_expanduser),
        ):
            os.environ.pop("XAUTHORITY", None)
            args, warnings = build_run_args(scratch_instance, is_fedora=False)

        assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" in args
        assert "DISPLAY=:0" in args
        # No XAUTHORITY mount or env
        assert "/tmp/.container-Xauthority:ro" not in " ".join(args)
        assert "XAUTHORITY=/tmp/.container-Xauthority" not in args

    def test_x11_and_gpu_combined(self, scratch_instance):
        """Both X11 and GPU args present when both enabled."""
        scratch_instance.config.x11 = True
        scratch_instance.config.gpu = True

        def mock_isdir(path):
            if path == "/tmp/.X11-unix":
                return True
            return _real_isdir(path)

        def mock_exists(path):
            if str(path).endswith(".Xauthority"):
                return False
            return _real_exists(path)

        def mock_expanduser(path):
            if path == "~/.Xauthority":
                return "/home/testuser/.Xauthority"
            return _real_expanduser(path)

        with (
            patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False),
            patch("scratch_monkey.run_args.os.path.isdir", side_effect=mock_isdir),
            patch("scratch_monkey.run_args.os.path.exists", side_effect=mock_exists),
            patch("scratch_monkey.run_args.os.path.expanduser", side_effect=mock_expanduser),
            patch("scratch_monkey.run_args.gpu_devices", return_value=["/dev/dri"]),
        ):
            os.environ.pop("XAUTHORITY", None)
            args, warnings = build_run_args(scratch_instance, is_fedora=False)

        # X11 mounts present
        assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" in args
        assert "DISPLAY=:0" in args
        # GPU device present
        assert "--device" in args
        assert "/dev/dri" in args
