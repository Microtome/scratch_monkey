"""Tests for scratch_monkey.overlay module."""

import os
from unittest.mock import patch

from scratch_monkey.config import InstanceConfig
from scratch_monkey.container import PodmanError
from scratch_monkey.instance import Instance
from scratch_monkey.overlay import (
    _ensure_overlay_id,
    _setup_fedora_user,
    ensure_running,
    exec_shell,
    reset,
)

# ─── _ensure_overlay_id ───────────────────────────────────────────────────────


def test_ensure_overlay_id_returns_existing(scratch_instance):
    """When overlay_id is already set, _ensure_overlay_id returns it directly."""
    scratch_instance.config.overlay_id = "sm-aabbccdd"
    result = _ensure_overlay_id(scratch_instance)
    assert result == "sm-aabbccdd"


def test_ensure_overlay_id_generates_and_saves_when_empty(tmp_path):
    """When overlay_id is empty, _ensure_overlay_id generates one and saves it."""
    inst_dir = tmp_path / "geninstance"
    inst_dir.mkdir()
    (inst_dir / "home").mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev\n")
    (inst_dir / "scratch.toml").write_text("")
    (inst_dir / ".env").touch()
    inst = Instance(
        name="geninstance",
        directory=inst_dir,
        config=InstanceConfig(),
        home_dir=inst_dir / "home",
    )
    assert inst.config.overlay_id == ""

    result = _ensure_overlay_id(inst)

    # Should have generated a valid overlay_id
    import re
    assert re.fullmatch(r"sm-[0-9a-f]{8}", result), f"Bad format: {result!r}"
    # Should have mutated config
    assert inst.config.overlay_id == result
    # Should have persisted to disk
    from scratch_monkey.config import load
    saved = load(inst_dir / "scratch.toml")
    assert saved.overlay_id == result


# ─── ensure_running ───────────────────────────────────────────────────────────


class TestEnsureRunning:
    def test_creates_container_if_missing(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        mock_runner.run_daemon.assert_called_once()

    def test_starts_stopped_container(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = True
        mock_runner.container_running.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        mock_runner.start.assert_called_once_with("sm-testtest")
        mock_runner.run_daemon.assert_not_called()

    def test_does_nothing_if_already_running(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = True
        mock_runner.container_running.return_value = True
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        mock_runner.run_daemon.assert_not_called()
        mock_runner.start.assert_not_called()

    def test_returns_container_name(self, scratch_instance, mock_runner):
        name = ensure_running(scratch_instance, mock_runner, "scratch_dev")
        assert name == "sm-testtest"

    def test_skips_user_setup_for_scratch(self, scratch_instance, mock_runner):
        """Scratch instances must NOT run useradd/sudoers setup."""
        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        # exec_capture should not be called for useradd on scratch instances
        for call_args in mock_runner.exec_capture.call_args_list:
            args = call_args[0][1]  # exec_args list
            assert "useradd" not in args, "useradd must not run on scratch instances"

    def test_runs_user_setup_for_fedora(self, fedora_instance, mock_runner):
        """Fedora instances MUST run useradd + sudoers setup."""
        mock_runner.container_exists.return_value = False
        mock_runner.exec_capture.return_value = ""
        ensure_running(fedora_instance, mock_runner, "scratch_dev_fedora")
        # Should have called exec_capture for user setup
        mock_runner.exec_capture.assert_called()
        all_calls = mock_runner.exec_capture.call_args_list
        # At least one call should involve useradd
        useradd_called = any(
            "useradd" in str(c) for c in all_calls
        )
        assert useradd_called, "useradd should be called for fedora instances"

    def test_includes_host_mounts_for_scratch(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = False
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        call_args = mock_runner.run_daemon.call_args
        run_args = call_args[0][2]  # third positional arg is run_args list
        assert "/usr:/usr:ro" in run_args

    def test_no_host_mounts_for_fedora(self, fedora_instance, mock_runner):
        mock_runner.container_exists.return_value = False
        mock_runner.exec_capture.return_value = ""
        ensure_running(fedora_instance, mock_runner, "scratch_dev_fedora")
        call_args = mock_runner.run_daemon.call_args
        run_args = call_args[0][2]
        assert "/usr:/usr:ro" not in run_args

    def test_setup_fedora_user_sudoers_uses_tee(self, fedora_instance, mock_runner):
        """Verify sudoers is written via tee+stdin, not shell interpolation."""
        mock_runner.container_exists.return_value = False
        mock_runner.container_running.return_value = False
        mock_runner.exec_capture.return_value = ""
        ensure_running(fedora_instance, mock_runner, "scratch_dev_fedora")

        calls = mock_runner.exec_capture.call_args_list
        tee_call = None
        chmod_call = None
        for c in calls:
            exec_args = c[0][1] if len(c[0]) > 1 else []
            if exec_args and exec_args[0] == "tee":
                tee_call = c
            if exec_args and exec_args[0] == "chmod":
                chmod_call = c

        assert tee_call is not None, "Expected a tee call for sudoers"
        tee_args = tee_call[0][1]
        assert "/etc/sudoers.d/" in tee_args[1]
        assert "NOPASSWD" in tee_call[1].get("input", "")
        assert tee_call[1].get("user") == "root"

        assert chmod_call is not None, "Expected a chmod call"
        assert chmod_call[0][1] == ["chmod", "440", tee_args[1]]
        assert chmod_call[1].get("user") == "root"

    def test_prints_warnings_to_stderr(self, scratch_instance, mock_runner, capsys):
        """Warnings from build_run_args should be printed to stderr."""
        mock_runner.container_exists.return_value = False
        scratch_instance.config.wayland = True
        with patch("os.path.exists", return_value=False):
            ensure_running(scratch_instance, mock_runner, "scratch_dev")
        captured = capsys.readouterr()
        assert "Warning:" in captured.err


# ─── _setup_fedora_user ───────────────────────────────────────────────────────


class TestSetupFedoraUser:
    def test_calls_useradd(self, mock_runner):
        mock_runner.exec_capture.return_value = ""
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)
        all_calls = mock_runner.exec_capture.call_args_list
        useradd_called = any("useradd" in str(c) for c in all_calls)
        assert useradd_called

    def test_calls_sudoers(self, mock_runner):
        mock_runner.exec_capture.return_value = ""
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)
        all_calls = mock_runner.exec_capture.call_args_list
        sudoers_called = any("sudoers" in str(c) for c in all_calls)
        assert sudoers_called

    def test_ignores_useradd_error(self, mock_runner):
        """useradd may fail if user already exists — should be tolerated."""
        mock_runner.exec_capture.side_effect = [
            "",  # sudo install
            PodmanError("useradd: user exists"),  # useradd
            "",  # sudoers (tee)
            "",  # chmod
        ]
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)  # should not raise

    def test_exec_capture_called_with_user_root(self, mock_runner):
        """All exec_capture calls must use user='root' for privileged setup."""
        mock_runner.exec_capture.return_value = ""
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)
        for call in mock_runner.exec_capture.call_args_list:
            assert call.kwargs.get("user") == "root", (
                f"exec_capture must be called with user='root', got: {call}"
            )

    def test_no_chown_called(self, mock_runner):
        """chown must NOT be called — --userns=keep-id handles ownership."""
        mock_runner.exec_capture.return_value = ""
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)
        all_calls = mock_runner.exec_capture.call_args_list
        chown_called = any("chown" in str(c) for c in all_calls)
        assert not chown_called, "chown must not be called when --userns=keep-id is used"


# ─── exec_shell ───────────────────────────────────────────────────────────────


class TestExecShell:
    def test_exec_as_user(self, scratch_instance, mock_runner):
        with patch.dict(os.environ, {"USER": "testuser"}):
            exec_shell(scratch_instance, mock_runner, "myinstance-overlay")
        mock_runner.exec_interactive.assert_called_once()
        call_args = mock_runner.exec_interactive.call_args
        container = call_args[0][0]
        exec_args = call_args[0][1]
        assert container == "myinstance-overlay"
        assert "--user" in exec_args
        assert "testuser" in exec_args
        # container_name should NOT be in exec_args (passed as separate param)
        assert "myinstance-overlay" not in exec_args

    def test_exec_as_root(self, scratch_instance, mock_runner):
        exec_shell(scratch_instance, mock_runner, "myinstance-overlay", root=True)
        call_args = mock_runner.exec_interactive.call_args
        container = call_args[0][0]
        exec_args = call_args[0][1]
        assert container == "myinstance-overlay"
        assert "--user" in exec_args
        user_idx = exec_args.index("--user")
        assert exec_args[user_idx + 1] == "root"
        assert "/root" in exec_args

    def test_passes_cmd(self, scratch_instance, mock_runner):
        exec_shell(scratch_instance, mock_runner, "myinstance-overlay", cmd="/bin/zsh")
        exec_args = mock_runner.exec_interactive.call_args[0][1]
        assert "/bin/zsh" in exec_args


# ─── reset ────────────────────────────────────────────────────────────────────


class TestReset:
    def test_removes_container(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = True
        result = reset(scratch_instance, mock_runner)
        assert result is True
        mock_runner.remove.assert_called_once_with("sm-testtest", force=True)

    def test_returns_false_if_no_container(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = False
        result = reset(scratch_instance, mock_runner)
        assert result is False
        mock_runner.remove.assert_not_called()
