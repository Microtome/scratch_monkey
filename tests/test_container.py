"""Tests for scratch_monkey.container module."""

import subprocess
import pytest
from unittest.mock import MagicMock, call, patch

from scratch_monkey.container import PodmanError, PodmanRunner


def make_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = stderr
    return r


@pytest.fixture
def runner():
    return PodmanRunner()


class TestImageExists:
    def test_returns_true_when_exists(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            assert runner.image_exists("myimage") is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "image" in args and "exists" in args and "myimage" in args

    def test_returns_false_when_missing(self, runner):
        with patch("subprocess.run", return_value=make_result(1)):
            assert runner.image_exists("missing") is False


class TestContainerExists:
    def test_returns_true_when_exists(self, runner):
        with patch("subprocess.run", return_value=make_result(0)):
            assert runner.container_exists("mycontainer") is True

    def test_returns_false_when_missing(self, runner):
        with patch("subprocess.run", return_value=make_result(1)):
            assert runner.container_exists("mycontainer") is False


class TestContainerRunning:
    def test_returns_true_when_running(self, runner):
        with patch("subprocess.run", return_value=make_result(0, stdout="true")):
            assert runner.container_running("mycontainer") is True

    def test_returns_false_when_not_running(self, runner):
        results = [make_result(0), make_result(0, stdout="false")]
        with patch("subprocess.run", side_effect=results):
            assert runner.container_running("mycontainer") is False

    def test_returns_false_when_not_exists(self, runner):
        with patch("subprocess.run", return_value=make_result(1)):
            assert runner.container_running("mycontainer") is False


class TestContainerStatus:
    def test_returns_empty_when_not_exists(self, runner):
        with patch("subprocess.run", return_value=make_result(1)):
            assert runner.container_status("mycontainer") == ""

    def test_returns_status_string(self, runner):
        results = [make_result(0), make_result(0, stdout="running")]
        with patch("subprocess.run", side_effect=results):
            assert runner.container_status("mycontainer") == "running"


class TestStart:
    def test_calls_start(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.start("mycontainer")
            args = mock_run.call_args[0][0]
            assert "start" in args and "mycontainer" in args

    def test_raises_on_failure(self, runner):
        with patch("subprocess.run", return_value=make_result(1, stderr="no such container")):
            with pytest.raises(PodmanError):
                runner.start("missing")


class TestRemove:
    def test_calls_rm(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.remove("mycontainer")
            args = mock_run.call_args[0][0]
            assert "rm" in args and "mycontainer" in args

    def test_force_flag(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.remove("mycontainer", force=True)
            args = mock_run.call_args[0][0]
            assert "--force" in args

    def test_raises_on_failure(self, runner):
        with patch("subprocess.run", return_value=make_result(1, stderr="error")):
            with pytest.raises(PodmanError):
                runner.remove("missing")


class TestRmi:
    def test_calls_rmi(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.rmi("myimage")
            args = mock_run.call_args[0][0]
            assert "rmi" in args and "myimage" in args

    def test_raises_on_failure(self, runner):
        with patch("subprocess.run", return_value=make_result(1, stderr="error")):
            with pytest.raises(PodmanError):
                runner.rmi("missing")


class TestBuild:
    def test_calls_build_with_tag_and_context(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.build("mytag", "/context")
            args = mock_run.call_args[0][0]
            assert "build" in args
            assert "-t" in args
            assert "mytag" in args
            assert "/context" in args

    def test_dockerfile_flag(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.build("mytag", "/context", dockerfile="/path/Dockerfile")
            args = mock_run.call_args[0][0]
            assert "-f" in args
            assert "/path/Dockerfile" in args

    def test_raises_on_failure(self, runner):
        with patch("subprocess.run", return_value=make_result(1, stderr="build failed")):
            with pytest.raises(PodmanError):
                runner.build("tag", "ctx")


class TestRunDaemon:
    def test_calls_run_with_daemon_args(self, runner):
        with patch("subprocess.run", return_value=make_result(0)) as mock_run:
            runner.run_daemon("mycontainer", "myimage", ["--network=host"])
            args = mock_run.call_args[0][0]
            assert "run" in args
            assert "-d" in args
            assert "--name" in args
            assert "mycontainer" in args
            assert "myimage" in args
            assert "sleep" in args
            assert "infinity" in args


class TestPodmanError:
    def test_attributes(self):
        err = PodmanError("failed", returncode=1, stderr="oops")
        assert err.returncode == 1
        assert err.stderr == "oops"
        assert "failed" in str(err)
