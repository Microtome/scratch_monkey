"""Tests for scratch_monkey.overlay module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from scratch_monkey.config import InstanceConfig
from scratch_monkey.container import PodmanError, PodmanRunner
from scratch_monkey.instance import Instance
from scratch_monkey.overlay import (
    _overlay_name,
    _setup_fedora_user,
    ensure_running,
    exec_shell,
    reset,
)


@pytest.fixture
def mock_runner():
    runner = MagicMock(spec=PodmanRunner)
    runner.container_exists.return_value = False
    runner.container_running.return_value = False
    runner.image_exists.return_value = False
    return runner


@pytest.fixture
def scratch_instance(tmp_path):
    inst_dir = tmp_path / "myinstance"
    inst_dir.mkdir()
    (inst_dir / "home").mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev\n")
    (inst_dir / "scratch.toml").write_text("")
    (inst_dir / ".env").touch()
    return Instance(
        name="myinstance",
        directory=inst_dir,
        config=InstanceConfig(),
        home_dir=inst_dir / "home",
    )


@pytest.fixture
def fedora_instance(tmp_path):
    inst_dir = tmp_path / "fedorainst"
    inst_dir.mkdir()
    (inst_dir / "home").mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev_fedora\n")
    (inst_dir / "scratch.toml").write_text("")
    (inst_dir / ".env").touch()
    return Instance(
        name="fedorainst",
        directory=inst_dir,
        config=InstanceConfig(),
        home_dir=inst_dir / "home",
    )


# ─── _overlay_name ────────────────────────────────────────────────────────────


def test_overlay_name(scratch_instance):
    assert _overlay_name(scratch_instance) == "myinstance-overlay"


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
        mock_runner.start.assert_called_once_with("myinstance-overlay")
        mock_runner.run_daemon.assert_not_called()

    def test_does_nothing_if_already_running(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = True
        mock_runner.container_running.return_value = True
        ensure_running(scratch_instance, mock_runner, "scratch_dev")
        mock_runner.run_daemon.assert_not_called()
        mock_runner.start.assert_not_called()

    def test_returns_container_name(self, scratch_instance, mock_runner):
        name = ensure_running(scratch_instance, mock_runner, "scratch_dev")
        assert name == "myinstance-overlay"

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
            "",  # sudoers
        ]
        with patch.dict(os.environ, {"USER": "testuser"}):
            _setup_fedora_user("mycontainer", mock_runner)  # should not raise


# ─── exec_shell ───────────────────────────────────────────────────────────────


class TestExecShell:
    def test_exec_as_user(self, scratch_instance, mock_runner):
        with patch.dict(os.environ, {"USER": "testuser"}):
            exec_shell(scratch_instance, mock_runner, "myinstance-overlay")
        mock_runner._run.assert_called_once()
        args = mock_runner._run.call_args[0][0]
        assert "exec" in args
        assert "--user" in args
        assert "testuser" in args

    def test_exec_as_root(self, scratch_instance, mock_runner):
        exec_shell(scratch_instance, mock_runner, "myinstance-overlay", root=True)
        args = mock_runner._run.call_args[0][0]
        assert "--user" not in args
        assert "/root" in args

    def test_passes_cmd(self, scratch_instance, mock_runner):
        exec_shell(scratch_instance, mock_runner, "myinstance-overlay", cmd="/bin/zsh")
        args = mock_runner._run.call_args[0][0]
        assert "/bin/zsh" in args


# ─── reset ────────────────────────────────────────────────────────────────────


class TestReset:
    def test_removes_container(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = True
        result = reset(scratch_instance, mock_runner)
        assert result is True
        mock_runner.remove.assert_called_once_with("myinstance-overlay", force=True)

    def test_returns_false_if_no_container(self, scratch_instance, mock_runner):
        mock_runner.container_exists.return_value = False
        result = reset(scratch_instance, mock_runner)
        assert result is False
        mock_runner.remove.assert_not_called()
