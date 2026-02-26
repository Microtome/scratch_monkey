"""Tests for the scratch-monkey CLI gui subcommand."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from scratch_monkey.cli.main import cli
from scratch_monkey.gui.main import gui_cli


class TestGuiCommand:
    def test_gui_calls_launch_with_default_instances_dir(self):
        """gui command calls launch with the default instances_dir."""
        runner = CliRunner()
        mock_launch = MagicMock()
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(cli, ["gui"])
        assert result.exit_code == 0
        mock_launch.assert_called_once()
        call_kwargs = mock_launch.call_args
        passed_dir = call_kwargs.kwargs.get("instances_dir") or call_kwargs.args[0]
        assert passed_dir == Path.home() / "scratch-monkey"

    def test_gui_passes_custom_instances_dir(self, tmp_path):
        """gui command passes --instances-dir override to launch."""
        runner = CliRunner()
        mock_launch = MagicMock()
        custom_dir = str(tmp_path / "my-instances")
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(cli, ["--instances-dir", custom_dir, "gui"])
        assert result.exit_code == 0
        mock_launch.assert_called_once()
        call_kwargs = mock_launch.call_args
        passed_dir = call_kwargs.kwargs.get("instances_dir") or call_kwargs.args[0]
        assert passed_dir == Path(custom_dir)

    def test_gui_import_error_exits_with_code_1(self):
        """gui command exits 1 with helpful message when GUI deps are missing."""
        # CliRunner mixes stderr into output by default in Click 8.x
        runner = CliRunner()

        class _FailModule:
            """Simulates a missing GUI module by raising ImportError on attribute access."""

            def __getattr__(self, name: str) -> None:
                raise ImportError("No module named 'enaml'")

        saved = sys.modules.get("scratch_monkey.gui.main")
        sys.modules["scratch_monkey.gui.main"] = _FailModule()  # type: ignore[assignment]
        try:
            result = runner.invoke(cli, ["gui"])
        finally:
            if saved is None:
                sys.modules.pop("scratch_monkey.gui.main", None)
            else:
                sys.modules["scratch_monkey.gui.main"] = saved

        assert result.exit_code == 1
        assert "GUI dependencies not installed" in result.output


class TestGuiCliStandalone:
    """Tests for gui/main.py:gui_cli() Click command."""

    def test_gui_cli_default_instances_dir(self):
        """gui_cli uses the default instances dir when no option or env var given."""
        runner = CliRunner()
        mock_launch = MagicMock()
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(gui_cli, [])
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(Path.home() / "scratch-monkey")

    def test_gui_cli_instances_dir_option(self, tmp_path):
        """gui_cli uses --instances-dir when provided."""
        runner = CliRunner()
        mock_launch = MagicMock()
        custom_dir = tmp_path / "custom-instances"
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(gui_cli, ["--instances-dir", str(custom_dir)])
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(custom_dir)

    def test_gui_cli_env_var(self, tmp_path):
        """gui_cli uses SCRATCH_MONKEY_INSTANCES_DIR env var when no CLI option given."""
        runner = CliRunner()
        mock_launch = MagicMock()
        env_dir = tmp_path / "env-instances"
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(
                gui_cli, [], env={"SCRATCH_MONKEY_INSTANCES_DIR": str(env_dir)}
            )
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(env_dir)

    def test_gui_cli_option_takes_precedence_over_env_var(self, tmp_path):
        """gui_cli --instances-dir takes precedence over env var."""
        runner = CliRunner()
        mock_launch = MagicMock()
        env_dir = tmp_path / "env-instances"
        cli_dir = tmp_path / "cli-instances"
        with patch("scratch_monkey.gui.main.launch", mock_launch):
            result = runner.invoke(
                gui_cli,
                ["--instances-dir", str(cli_dir)],
                env={"SCRATCH_MONKEY_INSTANCES_DIR": str(env_dir)},
            )
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(cli_dir)

    def test_gui_cli_help(self):
        """gui_cli --help returns exit code 0 and shows usage."""
        runner = CliRunner()
        result = runner.invoke(gui_cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--instances-dir" in result.output
