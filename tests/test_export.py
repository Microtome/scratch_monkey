"""Tests for scratch_monkey.export module."""

import stat

import pytest

from scratch_monkey.config import InstanceConfig
from scratch_monkey.export import _EXPORT_MAGIC, ExportError, export_command, unexport
from scratch_monkey.instance import Instance


@pytest.fixture
def instance(tmp_path):
    inst_dir = tmp_path / "myinstance"
    inst_dir.mkdir()
    home_dir = inst_dir / "home"
    home_dir.mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_monkey\n")
    return Instance(
        name="myinstance",
        directory=inst_dir,
        config=InstanceConfig(),
        home_dir=home_dir,
    )


@pytest.fixture
def bin_dir(tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    return d


# ─── export_command ───────────────────────────────────────────────────────────


class TestExportCommand:
    def test_creates_script(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        assert out.exists()
        assert out.name == "git"

    def test_custom_bin_name(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_name="mygit", bin_dir=bin_dir)
        assert out.name == "mygit"

    def test_script_is_executable(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        assert out.stat().st_mode & stat.S_IEXEC

    def test_script_has_shebang(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert content.startswith("#!/bin/sh")

    def test_script_has_magic_comment(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert _EXPORT_MAGIC in content

    def test_script_contains_instance_name(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert "myinstance" in content

    def test_script_contains_command(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert "/usr/bin/git" in content

    def test_script_contains_home_dir(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert str(instance.home_dir) in content

    def test_script_checks_scratch_instance_env(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert "SCRATCH_INSTANCE" in content

    def test_script_checks_overlay_container(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert "myinstance-overlay" in content

    def test_creates_bin_dir_if_missing(self, instance, tmp_path):
        new_bin_dir = tmp_path / "new" / "bin"
        assert not new_bin_dir.exists()
        export_command(instance, "/usr/bin/git", bin_dir=new_bin_dir)
        assert new_bin_dir.exists()

    def test_export_uses_overlay_id(self, tmp_path, bin_dir):
        """When overlay_id is set, the exported script uses it instead of '{name}-overlay'."""
        inst_dir = tmp_path / "myinstance"
        inst_dir.mkdir()
        home_dir = inst_dir / "home"
        home_dir.mkdir()
        (inst_dir / "Dockerfile").write_text("FROM scratch_monkey\n")
        inst = Instance(
            name="myinstance",
            directory=inst_dir,
            config=InstanceConfig(overlay_id="sm-abcd1234"),
            home_dir=home_dir,
        )
        out = export_command(inst, "/usr/bin/git", bin_dir=bin_dir)
        content = out.read_text()
        assert "sm-abcd1234" in content
        assert "myinstance-overlay" not in content


# ─── unexport ─────────────────────────────────────────────────────────────────


class TestUnexport:
    def test_removes_exported_script(self, instance, bin_dir):
        out = export_command(instance, "/usr/bin/git", bin_dir=bin_dir)
        assert out.exists()
        unexport("git", bin_dir=bin_dir)
        assert not out.exists()

    def test_raises_if_file_missing(self, bin_dir):
        with pytest.raises(ExportError, match="No file found"):
            unexport("nonexistent", bin_dir=bin_dir)

    def test_raises_if_not_scratch_monkey_export(self, bin_dir):
        script = bin_dir / "myscript"
        script.write_text("#!/bin/sh\necho hello\n")
        with pytest.raises(ExportError, match="does not look like"):
            unexport("myscript", bin_dir=bin_dir)

    def test_does_not_remove_non_export(self, bin_dir):
        script = bin_dir / "myscript"
        script.write_text("#!/bin/sh\necho hello\n")
        try:
            unexport("myscript", bin_dir=bin_dir)
        except ExportError:
            pass
        assert script.exists()
