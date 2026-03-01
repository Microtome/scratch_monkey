"""Tests for scratch_monkey.shared module."""

from pathlib import Path

import pytest

from scratch_monkey.config import InstanceConfig, load
from scratch_monkey.instance import Instance
from scratch_monkey.shared import (
    SharedError,
    add_to_instance,
    create_shared,
    delete_shared,
    list_shared,
    parse_shared_entry,
    remove_from_instance,
)


@pytest.fixture
def instances_dir(tmp_path):
    d = tmp_path / "scratch-monkey"
    d.mkdir()
    return d


def make_instance(instances_dir: Path, name: str, shared: list[str] | None = None) -> Instance:
    inst_dir = instances_dir / name
    inst_dir.mkdir()
    (inst_dir / "home").mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_monkey\n")
    cfg = InstanceConfig(shared=shared or [])
    from scratch_monkey.config import save
    save(inst_dir / "scratch.toml", cfg)
    return Instance(
        name=name,
        directory=inst_dir,
        config=cfg,
        home_dir=inst_dir / "home",
    )


# ─── create_shared ────────────────────────────────────────────────────────────


class TestCreateShared:
    def test_creates_directory(self, instances_dir):
        path = create_shared("comms", instances_dir)
        assert path.is_dir()
        assert path == instances_dir / ".shared" / "comms"

    def test_raises_if_already_exists(self, instances_dir):
        create_shared("comms", instances_dir)
        with pytest.raises(SharedError, match="already exists"):
            create_shared("comms", instances_dir)


# ─── delete_shared ────────────────────────────────────────────────────────────


class TestDeleteShared:
    def test_removes_directory(self, instances_dir):
        create_shared("comms", instances_dir)
        delete_shared("comms", instances_dir)
        assert not (instances_dir / ".shared" / "comms").exists()

    def test_raises_if_not_exists(self, instances_dir):
        with pytest.raises(SharedError, match="not found"):
            delete_shared("comms", instances_dir)

    def test_removes_from_instance_configs(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms"])
        delete_shared("comms", instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert "comms" not in cfg.shared

    def test_removes_from_multiple_instances(self, instances_dir):
        create_shared("comms", instances_dir)
        inst1 = make_instance(instances_dir, "alpha", shared=["comms"])
        inst2 = make_instance(instances_dir, "beta", shared=["comms"])
        delete_shared("comms", instances_dir)
        assert "comms" not in load(inst1.directory / "scratch.toml").shared
        assert "comms" not in load(inst2.directory / "scratch.toml").shared

    def test_preserves_other_shared_volumes(self, instances_dir):
        create_shared("comms", instances_dir)
        create_shared("data", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms", "data"])
        delete_shared("comms", instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert "comms" not in cfg.shared
        assert "data" in cfg.shared

    def test_removes_ro_entries_from_instance_configs(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms:ro"])
        delete_shared("comms", instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert not any("comms" in s for s in cfg.shared)


# ─── add_to_instance ──────────────────────────────────────────────────────────


class TestAddToInstance:
    def test_adds_volume_to_config(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha")
        add_to_instance("comms", inst, instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert "comms" in cfg.shared

    def test_idempotent_if_already_present(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms"])
        add_to_instance("comms", inst, instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert cfg.shared.count("comms") == 1

    def test_raises_if_shared_volume_missing(self, instances_dir):
        inst = make_instance(instances_dir, "alpha")
        with pytest.raises(SharedError, match="does not exist"):
            add_to_instance("comms", inst, instances_dir)

    def test_updates_instance_config_in_memory(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha")
        add_to_instance("comms", inst, instances_dir)
        assert "comms" in inst.config.shared

    def test_idempotent_when_already_present_with_mode(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms:ro"])
        add_to_instance("comms", inst, instances_dir)
        cfg = load(inst.directory / "scratch.toml")
        assert sum(1 for s in cfg.shared if "comms" in s) == 1


# ─── remove_from_instance ─────────────────────────────────────────────────────


class TestRemoveFromInstance:
    def test_removes_volume_from_config(self, instances_dir):
        create_shared("comms", instances_dir)
        inst = make_instance(instances_dir, "alpha", shared=["comms"])
        result = remove_from_instance("comms", inst)
        assert result is True
        cfg = load(inst.directory / "scratch.toml")
        assert "comms" not in cfg.shared

    def test_returns_false_if_not_present(self, instances_dir):
        inst = make_instance(instances_dir, "alpha")
        result = remove_from_instance("comms", inst)
        assert result is False

    def test_preserves_other_volumes(self, instances_dir):
        inst = make_instance(instances_dir, "alpha", shared=["comms", "data"])
        remove_from_instance("comms", inst)
        cfg = load(inst.directory / "scratch.toml")
        assert "data" in cfg.shared
        assert "comms" not in cfg.shared

    def test_updates_instance_config_in_memory(self, instances_dir):
        inst = make_instance(instances_dir, "alpha", shared=["comms"])
        remove_from_instance("comms", inst)
        assert "comms" not in inst.config.shared

    def test_removes_volume_with_mode_suffix(self, instances_dir):
        inst = make_instance(instances_dir, "alpha", shared=["comms:ro"])
        result = remove_from_instance("comms", inst)
        assert result is True
        cfg = load(inst.directory / "scratch.toml")
        assert not any("comms" in s for s in cfg.shared)


# ─── list_shared ──────────────────────────────────────────────────────────────


class TestListShared:
    def test_empty_returns_empty(self, instances_dir):
        assert list_shared(instances_dir) == []

    def test_no_shared_dir_returns_empty(self, tmp_path):
        assert list_shared(tmp_path / "nonexistent") == []

    def test_lists_volumes(self, instances_dir):
        create_shared("comms", instances_dir)
        create_shared("data", instances_dir)
        result = list_shared(instances_dir)
        names = [v.name for v in result]
        assert "comms" in names
        assert "data" in names

    def test_shows_which_instances_use_volume(self, instances_dir):
        create_shared("comms", instances_dir)
        make_instance(instances_dir, "alpha", shared=["comms"])
        make_instance(instances_dir, "beta")
        result = list_shared(instances_dir)
        comms_info = next(v for v in result if v.name == "comms")
        assert "alpha" in comms_info.used_by
        assert "beta" not in comms_info.used_by

    def test_empty_used_by_for_unused_volume(self, instances_dir):
        create_shared("data", instances_dir)
        result = list_shared(instances_dir)
        data_info = result[0]
        assert data_info.used_by == []

    def test_counts_ro_entries_in_used_by(self, instances_dir):
        create_shared("comms", instances_dir)
        make_instance(instances_dir, "alpha", shared=["comms:ro"])
        result = list_shared(instances_dir)
        comms_info = next(v for v in result if v.name == "comms")
        assert "alpha" in comms_info.used_by


# ─── parse_shared_entry ───────────────────────────────────────────────────────


class TestParseSharedEntry:
    def test_bare_name_defaults_to_rw(self):
        assert parse_shared_entry("comms") == ("comms", "rw")

    def test_name_with_ro(self):
        assert parse_shared_entry("comms:ro") == ("comms", "ro")

    def test_name_with_rw(self):
        assert parse_shared_entry("comms:rw") == ("comms", "rw")

    def test_invalid_mode_raises(self):
        with pytest.raises(SharedError, match="Invalid shared volume mode"):
            parse_shared_entry("comms:invalid")
