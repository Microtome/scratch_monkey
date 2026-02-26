"""Shared test fixtures for scratch-monkey tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scratch_monkey.config import InstanceConfig, save
from scratch_monkey.container import PodmanRunner
from scratch_monkey.instance import Instance


@pytest.fixture
def mock_runner() -> MagicMock:
    """A PodmanRunner mock with sensible defaults."""
    runner = MagicMock(spec=PodmanRunner)
    runner.image_exists.return_value = False
    runner.container_exists.return_value = False
    runner.container_running.return_value = False
    runner.container_status.return_value = ""
    runner.exec_capture.return_value = ""
    return runner


@pytest.fixture
def instances_dir(tmp_path: Path) -> Path:
    """A temporary instances directory."""
    d = tmp_path / "scratch-monkey"
    d.mkdir()
    return d


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A temporary project directory with scratch.toml.default."""
    p = tmp_path / "project"
    p.mkdir()
    (p / "scratch.toml.default").write_text(
        "# scratch-monkey instance configuration\n"
    )
    return p


@pytest.fixture
def scratch_instance(tmp_path: Path) -> Instance:
    """A scratch-based instance fixture."""
    inst_dir = tmp_path / "instances" / "scratchinst"
    inst_dir.mkdir(parents=True)
    home_dir = inst_dir / "home"
    home_dir.mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev\n")
    cfg = InstanceConfig()
    save(inst_dir / "scratch.toml", cfg)
    (inst_dir / ".env").touch()
    return Instance(
        name="scratchinst",
        directory=inst_dir,
        config=cfg,
        home_dir=home_dir,
    )


@pytest.fixture
def fedora_instance(tmp_path: Path) -> Instance:
    """A fedora-based instance fixture."""
    inst_dir = tmp_path / "instances" / "fedorainst"
    inst_dir.mkdir(parents=True)
    home_dir = inst_dir / "home"
    home_dir.mkdir()
    (inst_dir / "Dockerfile").write_text("FROM scratch_dev_fedora\n")
    cfg = InstanceConfig()
    save(inst_dir / "scratch.toml", cfg)
    (inst_dir / ".env").touch()
    return Instance(
        name="fedorainst",
        directory=inst_dir,
        config=cfg,
        home_dir=home_dir,
    )
