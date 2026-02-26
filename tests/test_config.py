"""Tests for scratch_monkey.config module."""


import pytest

from scratch_monkey.config import (
    ConfigError,
    InstanceConfig,
    _serialize,
    load,
    save,
    validate_name,
)

# ─── validate_name ────────────────────────────────────────────────────────────


class TestValidateName:
    def test_simple_alphanum(self):
        validate_name("myproject")  # should not raise

    def test_starts_with_digit(self):
        validate_name("2cool")  # should not raise

    def test_with_dash(self):
        validate_name("my-project")  # should not raise

    def test_with_dot(self):
        validate_name("my.project")  # should not raise

    def test_with_underscore(self):
        validate_name("my_project")  # should not raise

    def test_empty_raises(self):
        with pytest.raises(ConfigError):
            validate_name("")

    def test_starts_with_dash_raises(self):
        with pytest.raises(ConfigError):
            validate_name("-myproject")

    def test_starts_with_dot_raises(self):
        with pytest.raises(ConfigError):
            validate_name(".myproject")

    def test_special_chars_raise(self):
        with pytest.raises(ConfigError):
            validate_name("my project")

    def test_slash_raises(self):
        with pytest.raises(ConfigError):
            validate_name("my/project")


# ─── load ─────────────────────────────────────────────────────────────────────


class TestLoad:
    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load(tmp_path / "nonexistent.toml")
        assert cfg == InstanceConfig()

    def test_empty_file_returns_defaults(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text("")
        cfg = load(toml)
        assert cfg == InstanceConfig()

    def test_parses_cmd(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text('cmd = "/bin/zsh"\n')
        cfg = load(toml)
        assert cfg.cmd == "/bin/zsh"

    def test_parses_booleans(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text("wayland = true\nssh = true\noverlay = true\n")
        cfg = load(toml)
        assert cfg.wayland is True
        assert cfg.ssh is True
        assert cfg.overlay is True

    def test_parses_string_arrays(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text(
            'volumes = ["/host/path:/container/path:ro", "/another:/path"]\n'
        )
        cfg = load(toml)
        assert cfg.volumes == ["/host/path:/container/path:ro", "/another:/path"]

    def test_parses_shared_list(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text('shared = ["comms", "data"]\n')
        cfg = load(toml)
        assert cfg.shared == ["comms", "data"]

    def test_parses_env_list(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text('env = ["FOO=bar", "BAZ=qux"]\n')
        cfg = load(toml)
        assert cfg.env == ["FOO=bar", "BAZ=qux"]

    def test_commented_lines_ignored(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text("# wayland = true\n# ssh = true\n")
        cfg = load(toml)
        assert cfg.wayland is False
        assert cfg.ssh is False

    def test_parses_home(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text('home = "/custom/home"\n')
        cfg = load(toml)
        assert cfg.home == "/custom/home"

    def test_full_config(self, tmp_path):
        toml = tmp_path / "scratch.toml"
        toml.write_text(
            'cmd = "/bin/zsh"\n'
            "wayland = true\n"
            "ssh = false\n"
            'home = ""\n'
            'volumes = ["/a:/b:ro"]\n'
            'env = ["X=1"]\n'
            'shared = ["comms"]\n'
            "overlay = true\n"
        )
        cfg = load(toml)
        assert cfg.cmd == "/bin/zsh"
        assert cfg.wayland is True
        assert cfg.ssh is False
        assert cfg.volumes == ["/a:/b:ro"]
        assert cfg.env == ["X=1"]
        assert cfg.shared == ["comms"]
        assert cfg.overlay is True


# ─── save ─────────────────────────────────────────────────────────────────────


class TestSave:
    def test_roundtrip_defaults(self, tmp_path):
        path = tmp_path / "scratch.toml"
        cfg = InstanceConfig()
        save(path, cfg)
        loaded = load(path)
        assert loaded == cfg

    def test_roundtrip_custom_values(self, tmp_path):
        path = tmp_path / "scratch.toml"
        cfg = InstanceConfig(
            cmd="/bin/zsh",
            wayland=True,
            ssh=True,
            home="/custom",
            volumes=["/a:/b:ro"],
            env=["X=1"],
            shared=["comms"],
            overlay=True,
        )
        save(path, cfg)
        loaded = load(path)
        assert loaded == cfg

    def test_atomic_write_creates_file(self, tmp_path):
        path = tmp_path / "scratch.toml"
        assert not path.exists()
        save(path, InstanceConfig())
        assert path.exists()

    def test_atomic_write_no_tmp_leftover(self, tmp_path):
        path = tmp_path / "scratch.toml"
        save(path, InstanceConfig())
        tmp_files = list(tmp_path.glob(".scratch-monkey-*.tmp"))
        assert tmp_files == []

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "scratch.toml"
        save(path, InstanceConfig(wayland=True))
        save(path, InstanceConfig(wayland=False))
        loaded = load(path)
        assert loaded.wayland is False


# ─── _serialize ───────────────────────────────────────────────────────────────


class TestSerialize:
    def test_contains_all_keys(self):
        text = _serialize(InstanceConfig())
        assert "cmd" in text
        assert "wayland" in text
        assert "ssh" in text
        assert "home" in text
        assert "volumes" in text
        assert "env" in text
        assert "shared" in text
        assert "overlay" in text

    def test_bool_lowercase(self):
        text = _serialize(InstanceConfig(wayland=True, overlay=False))
        assert "wayland = true" in text
        assert "overlay = false" in text

    def test_list_format(self):
        text = _serialize(InstanceConfig(volumes=["/a:/b:ro"]))
        assert 'volumes = ["/a:/b:ro"]' in text

    def test_escapes_quotes_in_strings(self):
        text = _serialize(InstanceConfig(cmd='/bin/bash -c "echo hi"'))
        assert '\\"' in text
