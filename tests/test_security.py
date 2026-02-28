"""Tests for security validation fixes."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from scratch_monkey.config import ConfigError, InstanceConfig, load, save
from scratch_monkey.export import ExportError, export_command, unexport
from scratch_monkey.instance import Instance
from scratch_monkey.shared import SharedError, create_shared, delete_shared


def _make_instance(tmp_path: Path, name: str = "testinst") -> Instance:
    """Helper to create a minimal Instance for testing."""
    inst_dir = tmp_path / "instances" / name
    inst_dir.mkdir(parents=True)
    (inst_dir / "home").mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev\n")
    cfg = InstanceConfig()
    save(inst_dir / "scratch.toml", cfg)
    return Instance(
        name=name,
        directory=inst_dir,
        config=cfg,
        home_dir=inst_dir / "home",
    )


# ─── cmd quoting in export scripts ───────────────────────────────────────────


class TestExportCmdQuoting:
    """Verify cmd is quoted in export scripts."""

    def test_cmd_with_spaces_is_quoted(self, tmp_path):
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        out = export_command(inst, "/usr/bin/my program", bin_dir=bin_dir)
        content = out.read_text()
        # shlex.quote wraps with single quotes so spaces are handled safely
        quoted = shlex.quote("/usr/bin/my program")
        assert quoted in content

    def test_simple_cmd_is_quoted(self, tmp_path):
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        out = export_command(inst, "/usr/bin/rg", bin_dir=bin_dir)
        content = out.read_text()
        # Simple paths are safe (no special chars), shlex.quote returns them as-is
        assert "/usr/bin/rg" in content

    def test_cmd_with_special_chars_is_quoted(self, tmp_path):
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        out = export_command(inst, "/usr/bin/my-tool", bin_dir=bin_dir)
        content = out.read_text()
        quoted = shlex.quote("/usr/bin/my-tool")
        assert quoted in content

    def test_raw_unquoted_cmd_not_in_script(self, tmp_path):
        """A cmd with spaces should NOT appear unquoted in the script."""
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        cmd = "/opt/my tools/program"
        out = export_command(inst, cmd, bin_dir=bin_dir)
        content = out.read_text()
        # The script should contain the quoted form
        assert shlex.quote(cmd) in content
        # The raw cmd should NOT appear as 'exec <cmd>' without quoting
        assert f"exec {cmd}" not in content


# ─── bin_name validation in unexport ─────────────────────────────────────────


class TestUnexportValidation:
    """Verify bin_name validation in unexport."""

    def test_rejects_path_traversal(self, tmp_path):
        with pytest.raises(ExportError, match="Invalid"):
            unexport("../etc/passwd", bin_dir=tmp_path)

    def test_rejects_slash_in_name(self, tmp_path):
        with pytest.raises(ExportError, match="Invalid"):
            unexport("foo/bar", bin_dir=tmp_path)

    def test_rejects_dotdot(self, tmp_path):
        with pytest.raises(ExportError, match="Invalid"):
            unexport("..", bin_dir=tmp_path)

    def test_rejects_single_dot(self, tmp_path):
        with pytest.raises(ExportError, match="Invalid"):
            unexport(".", bin_dir=tmp_path)

    def test_accepts_valid_name(self, tmp_path):
        """A valid script name does not raise on bin_name validation."""
        # No script exists at this path, so we get ExportError for "No file found"
        # rather than "Invalid" — confirming bin_name passed validation.
        with pytest.raises(ExportError, match="No file found"):
            unexport("myscript", bin_dir=tmp_path)


# ─── bin_name validation in export_command ───────────────────────────────────


class TestExportBinNameValidation:
    """Verify bin_name validation in export_command."""

    def test_rejects_slash_in_bin_name(self, tmp_path):
        inst = _make_instance(tmp_path)
        with pytest.raises(ExportError, match="Invalid"):
            export_command(inst, "/usr/bin/rg", bin_name="../evil", bin_dir=tmp_path / "bin")

    def test_rejects_dotdot_bin_name(self, tmp_path):
        inst = _make_instance(tmp_path)
        with pytest.raises(ExportError, match="Invalid"):
            export_command(inst, "/usr/bin/rg", bin_name="..", bin_dir=tmp_path / "bin")

    def test_rejects_dot_bin_name(self, tmp_path):
        inst = _make_instance(tmp_path)
        with pytest.raises(ExportError, match="Invalid"):
            export_command(inst, "/usr/bin/rg", bin_name=".", bin_dir=tmp_path / "bin")

    def test_rejects_empty_bin_name(self, tmp_path):
        inst = _make_instance(tmp_path)
        with pytest.raises(ExportError, match="Cannot derive"):
            export_command(inst, "", bin_dir=tmp_path / "bin")

    def test_accepts_valid_bin_name(self, tmp_path):
        inst = _make_instance(tmp_path)
        out = export_command(inst, "/usr/bin/rg", bin_name="my-rg", bin_dir=tmp_path / "bin")
        assert out.name == "my-rg"
        assert out.exists()


# ─── PATH-shadowing warning for export ───────────────────────────────────────


class TestExportPathShadowing:
    """Verify PATH-shadowing warning for common command names."""

    def test_warns_for_common_command(self, tmp_path, capsys):
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        export_command(inst, "/container/bin/git", bin_name="git", bin_dir=bin_dir)
        captured = capsys.readouterr()
        assert "shadows" in captured.err

    def test_no_warning_for_unique_name(self, tmp_path, capsys):
        inst = _make_instance(tmp_path)
        bin_dir = tmp_path / "bin"
        export_command(inst, "/container/bin/my-custom-tool", bin_dir=bin_dir)
        captured = capsys.readouterr()
        assert "shadows" not in captured.err


# ─── shared volume name validation ───────────────────────────────────────────


class TestSharedVolumeValidation:
    """Verify shared volume name validation."""

    def test_create_shared_rejects_traversal_name(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            create_shared("../etc", instances_dir)

    def test_create_shared_rejects_dotdot(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            create_shared("..", instances_dir)

    def test_create_shared_rejects_leading_dot(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            create_shared(".hidden", instances_dir)

    def test_create_shared_rejects_name_with_slash(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            create_shared("foo/bar", instances_dir)

    def test_delete_shared_rejects_traversal_name(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            delete_shared("../etc", instances_dir)

    def test_delete_shared_rejects_dotdot(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        with pytest.raises(SharedError):
            delete_shared("..", instances_dir)

    def test_create_shared_accepts_valid_name(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        path = create_shared("my-volume", instances_dir)
        assert path.is_dir()

    def test_create_shared_accepts_alphanumeric_name(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        path = create_shared("vol1", instances_dir)
        assert path.is_dir()


# ─── home path validation in config load ─────────────────────────────────────


class TestHomePathValidation:
    """Verify home path validation in config load."""

    def test_relative_home_path_raises(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = "relative/path"\n')
        with pytest.raises(ConfigError, match="absolute"):
            load(config_path)

    def test_dotdot_in_home_path_raises(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = "/home/user/../etc"\n')
        with pytest.raises(ConfigError, match=r"\.\."):
            load(config_path)

    def test_relative_home_no_slash_raises(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = "myhome"\n')
        with pytest.raises(ConfigError, match="absolute"):
            load(config_path)

    def test_valid_absolute_home_path_loads(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = "/custom/home/dir"\n')
        cfg = load(config_path)
        assert cfg.home == "/custom/home/dir"

    def test_empty_home_path_loads(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = ""\n')
        cfg = load(config_path)
        assert cfg.home == ""

    def test_missing_home_key_loads_with_default(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('cmd = "/bin/bash"\n')
        cfg = load(config_path)
        assert cfg.home == ""

    def test_valid_nested_absolute_home_path_loads(self, tmp_path):
        config_path = tmp_path / "scratch.toml"
        config_path.write_text('home = "/var/home/user/workdir"\n')
        cfg = load(config_path)
        assert cfg.home == "/var/home/user/workdir"
