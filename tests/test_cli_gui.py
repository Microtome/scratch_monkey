"""Tests for the scratch-monkey CLI gui subcommand."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from scratch_monkey.cli.main import cli


class TestGuiCommand:
    def test_gui_calls_main_with_default_instances_dir(self):
        """gui command calls gui_main with the default instances_dir."""
        runner = CliRunner()
        mock_gui_main = MagicMock()
        with patch("scratch_monkey.gui.main.main", mock_gui_main):
            result = runner.invoke(cli, ["gui"])
        assert result.exit_code == 0
        mock_gui_main.assert_called_once()
        call_kwargs = mock_gui_main.call_args
        passed_dir = call_kwargs.kwargs.get("instances_dir") or call_kwargs.args[0]
        assert passed_dir == Path.home() / "scratch-monkey"

    def test_gui_passes_custom_instances_dir(self, tmp_path):
        """gui command passes --instances-dir override to gui_main."""
        runner = CliRunner()
        mock_gui_main = MagicMock()
        custom_dir = str(tmp_path / "my-instances")
        with patch("scratch_monkey.gui.main.main", mock_gui_main):
            result = runner.invoke(cli, ["--instances-dir", custom_dir, "gui"])
        assert result.exit_code == 0
        mock_gui_main.assert_called_once()
        call_kwargs = mock_gui_main.call_args
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
