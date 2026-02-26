"""Tests for scratch_monkey.gui.models volume support."""

import pytest

atom = pytest.importorskip("atom")

from scratch_monkey.config import InstanceConfig  # noqa: E402
from scratch_monkey.gui.models import (  # noqa: E402
    AppModel,
    InstanceModel,
    SharedVolumeEntry,
    VolumeMountEntry,
)
from scratch_monkey.instance import InstanceInfo  # noqa: E402


class TestVolumeMountEntry:
    def test_from_spec_host_container(self):
        e = VolumeMountEntry.from_spec("/host:/container")
        assert e.host_path == "/host"
        assert e.container_path == "/container"
        assert e.mode == "rw"

    def test_from_spec_with_mode(self):
        e = VolumeMountEntry.from_spec("/host:/container:ro")
        assert e.host_path == "/host"
        assert e.container_path == "/container"
        assert e.mode == "ro"

    def test_to_spec_rw_omits_mode(self):
        e = VolumeMountEntry(host_path="/a", container_path="/b", mode="rw")
        assert e.to_spec() == "/a:/b"

    def test_to_spec_ro_includes_mode(self):
        e = VolumeMountEntry(host_path="/a", container_path="/b", mode="ro")
        assert e.to_spec() == "/a:/b:ro"

    def test_round_trip(self):
        original = "/data:/mnt/data:ro"
        e = VolumeMountEntry.from_spec(original)
        assert e.to_spec() == original

    def test_round_trip_rw(self):
        original = "/data:/mnt/data"
        e = VolumeMountEntry.from_spec(original)
        assert e.to_spec() == original


class TestInstanceModelVolumes:
    def _make_info(self, volumes=None, shared=None):
        cfg = InstanceConfig(
            volumes=volumes or [],
            shared=shared or [],
        )
        return InstanceInfo(
            name="test",
            directory="/tmp/test",
            image_built=False,
            overlay_running=False,
            config=cfg,
        )

    def test_from_info_populates_volume_entries(self):
        info = self._make_info(volumes=["/host:/container", "/a:/b:ro"])
        m = InstanceModel.from_info(info)
        assert len(m.volume_entries) == 2
        assert m.volume_entries[0].host_path == "/host"
        assert m.volume_entries[1].mode == "ro"

    def test_to_config_serializes_volume_entries(self):
        m = InstanceModel()
        m.volume_entries = [
            VolumeMountEntry(host_path="/a", container_path="/b", mode="rw"),
            VolumeMountEntry(host_path="/c", container_path="/d", mode="ro"),
        ]
        cfg = m.to_config()
        assert cfg.volumes == ["/a:/b", "/c:/d:ro"]

    def test_to_config_serializes_shared_entries(self):
        m = InstanceModel()
        m.shared_entries = [
            SharedVolumeEntry(name="comms", enabled=True, mode="rw"),
            SharedVolumeEntry(name="data", enabled=True, mode="ro"),
            SharedVolumeEntry(name="unused", enabled=False, mode="rw"),
        ]
        cfg = m.to_config()
        assert "comms" in cfg.shared
        assert "data:ro" in cfg.shared
        assert all("unused" not in s for s in cfg.shared)

    def test_add_volume_entry(self):
        m = InstanceModel()
        assert len(m.volume_entries) == 0
        m.add_volume_entry()
        assert len(m.volume_entries) == 1

    def test_remove_volume_entry(self):
        m = InstanceModel()
        m.volume_entries = [
            VolumeMountEntry(host_path="/a", container_path="/b"),
            VolumeMountEntry(host_path="/c", container_path="/d"),
        ]
        m.remove_volume_entry(0)
        assert len(m.volume_entries) == 1
        assert m.volume_entries[0].host_path == "/c"


class TestAppModelSharedEntries:
    def test_init_shared_entries_marks_enabled(self, tmp_path):
        """init_shared_entries should mark instance's shared volumes as enabled."""
        # Set up instances dir with a shared volume
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        shared_dir = instances_dir / ".shared"
        shared_dir.mkdir()
        (shared_dir / "comms").mkdir()
        (shared_dir / "data").mkdir()

        # Create AppModel (will try to list instances, which is fine with empty dir)
        from unittest.mock import MagicMock
        runner = MagicMock()
        runner.container_exists.return_value = False
        runner.container_running.return_value = False
        runner.image_exists.return_value = False
        app = AppModel(instances_dir=instances_dir, runner=runner)

        # Create a model with comms enabled
        m = InstanceModel()
        m.shared = ["comms"]
        app.init_shared_entries(m)

        assert len(m.shared_entries) == 2
        comms = next(e for e in m.shared_entries if e.name == "comms")
        data = next(e for e in m.shared_entries if e.name == "data")
        assert comms.enabled is True
        assert comms.mode == "rw"
        assert data.enabled is False

    def test_init_shared_entries_parses_mode(self, tmp_path):
        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        shared_dir = instances_dir / ".shared"
        shared_dir.mkdir()
        (shared_dir / "comms").mkdir()

        from unittest.mock import MagicMock
        runner = MagicMock()
        runner.container_exists.return_value = False
        runner.container_running.return_value = False
        runner.image_exists.return_value = False
        app = AppModel(instances_dir=instances_dir, runner=runner)

        m = InstanceModel()
        m.shared = ["comms:ro"]
        app.init_shared_entries(m)

        comms = next(e for e in m.shared_entries if e.name == "comms")
        assert comms.enabled is True
        assert comms.mode == "ro"


class TestGUISmoke:
    """Smoke tests to verify the GUI import chain works."""

    def test_gui_main_module_imports(self):
        """Verify scratch_monkey.gui.main can be imported."""
        from scratch_monkey.gui import main  # noqa: F401

    def test_models_import_chain(self):
        """Verify all model classes are importable."""
        from scratch_monkey.gui.models import (  # noqa: F401
            AppModel,
            InstanceModel,
            SharedVolumeEntry,
            VolumeMountEntry,
        )

    def test_app_model_creates_with_empty_dir(self, tmp_path):
        """Verify AppModel can be created with an empty instances dir."""
        from unittest.mock import MagicMock

        from scratch_monkey.gui.models import AppModel

        runner = MagicMock()
        runner.container_exists.return_value = False
        runner.container_running.return_value = False
        runner.image_exists.return_value = False

        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()
        app = AppModel(instances_dir=instances_dir, runner=runner)
        assert app.instances == []
        assert app.status_message.startswith("Loaded")

    def test_enaml_views_compile(self):
        """Verify all enaml view files compile without errors."""
        import enaml
        with enaml.imports():
            from scratch_monkey.gui.views import (
                config_editor,  # noqa: F401
                create_dialog,  # noqa: F401
                instance_detail,  # noqa: F401
                instance_list,  # noqa: F401
                main_window,  # noqa: F401
            )


class TestAppModelCreateInstance:
    """Tests for AppModel.create_instance()."""

    def _make_app(self, tmp_path):
        from unittest.mock import MagicMock, patch

        instances_dir = tmp_path / "scratch-monkey"
        instances_dir.mkdir()

        runner = MagicMock()
        runner.container_exists.return_value = False
        runner.container_running.return_value = False
        runner.image_exists.return_value = False

        # Patch _PROJECT_DIR to use a temp dir with scratch.toml.default
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            app = AppModel(instances_dir=instances_dir, runner=runner)

        return app, instances_dir, project_dir

    def test_create_success(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)
        assert len(app.instances) == 0

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            result = app.create_instance("myinst")

        assert result == ""
        assert (instances_dir / "myinst").is_dir()
        assert (instances_dir / "myinst" / "scratch.toml").exists()
        assert app.selected_instance == "myinst"
        assert any(i.name == "myinst" for i in app.instances)

    def test_create_invalid_name(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            result = app.create_instance("bad name!")

        assert result != ""
        assert len(app.instances) == 0

    def test_create_duplicate(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            app.create_instance("dup")
            result = app.create_instance("dup")

        assert result != ""

    def test_create_fedora(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            result = app.create_instance("fed", fedora=True)

        assert result == ""
        dockerfile = (instances_dir / "fed" / "Dockerfile").read_text()
        assert "fedora" in dockerfile.lower()

    def test_create_selects_new_instance(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            app.create_instance("first")
            app.create_instance("second")

        assert app.selected_instance == "second"

    def test_create_with_config_override(self, tmp_path):
        from unittest.mock import patch

        from scratch_monkey.config import InstanceConfig, load

        app, instances_dir, project_dir = self._make_app(tmp_path)

        custom_cfg = InstanceConfig(cmd="/bin/zsh", wayland=True, env=["EDITOR=vim"])

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            result = app.create_instance("configured", config=custom_cfg)

        assert result == ""
        saved = load(instances_dir / "configured" / "scratch.toml")
        assert saved.cmd == "/bin/zsh"
        assert saved.wayland is True
        assert "EDITOR=vim" in saved.env

    def test_create_without_config_uses_default(self, tmp_path):
        from unittest.mock import patch

        from scratch_monkey.config import load

        app, instances_dir, project_dir = self._make_app(tmp_path)

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            result = app.create_instance("default-cfg")

        assert result == ""
        saved = load(instances_dir / "default-cfg" / "scratch.toml")
        assert saved.cmd == "/bin/bash"  # default

    def test_new_instance_model(self, tmp_path):
        from unittest.mock import patch

        app, instances_dir, project_dir = self._make_app(tmp_path)

        # Add a shared volume
        shared_dir = instances_dir / ".shared"
        shared_dir.mkdir()
        (shared_dir / "comms").mkdir()

        with patch("scratch_monkey.gui.models._PROJECT_DIR", project_dir):
            app.refresh()
            m = app.new_instance_model()

        assert isinstance(m, InstanceModel)
        assert len(m.shared_entries) == 1
        assert m.shared_entries[0].name == "comms"


class TestInstanceModelEnvVars:
    def test_add_env_var_default(self):
        m = InstanceModel()
        m.add_env_var()
        assert m.env_vars == [""]

    def test_add_env_var_with_value(self):
        m = InstanceModel()
        m.add_env_var("FOO=bar")
        assert m.env_vars == ["FOO=bar"]

    def test_remove_env_var(self):
        m = InstanceModel()
        m.env_vars = ["A=1", "B=2", "C=3"]
        m.remove_env_var(1)
        assert m.env_vars == ["A=1", "C=3"]

    def test_remove_env_var_out_of_range(self):
        m = InstanceModel()
        m.env_vars = ["A=1"]
        m.remove_env_var(5)
        assert m.env_vars == ["A=1"]

    def test_to_config_includes_env(self):
        m = InstanceModel()
        m.env_vars = ["FOO=bar", "BAZ=qux"]
        cfg = m.to_config()
        assert cfg.env == ["FOO=bar", "BAZ=qux"]
