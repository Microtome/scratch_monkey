# scratch-monkey: Specification

## Overview

`scratch-monkey` is a Python CLI and GUI tool for managing Podman-based dev container instances. It replaces the bash/justfile-only approach of the earlier `scratch_dev` with a proper Python package, a Click CLI, and an Enaml GUI.

## Key Improvements Over bash Predecessor

| Problem | Fix |
|---------|-----|
| TOML parsed with grep/sed | `tomllib` (stdlib, Python 3.11+) proper parser |
| Config mutation with `sed -i` | Atomic write via temp file + `os.replace()` |
| `head -1` vs `tail -1` inconsistency on FROM | Consistent: always use **last** FROM (final stage) |
| Overlay sudo setup runs on scratch containers | Skipped entirely when base is `scratch`-based |
| No instance name validation | Validated against `[a-zA-Z0-9][a-zA-Z0-9_.-]*` |
| Array config values unreliable | Proper TOML array parsing |
| No tests | 80%+ unit test coverage, all mocked at the podman boundary |

---

## Project Layout

```
scratch-monkey/
├── pyproject.toml             # package metadata, deps, entry points
├── .python-version            # pins Python 3.11+
├── justfile                   # DEV ONLY: test, lint, install, build
├── install.sh                 # end-user install script
├── README.md
├── Dockerfile                 # scratch base image
├── Dockerfile.fedora          # fedora base image
├── scratch.toml.default       # config template
├── specs/
│   ├── redesign.md            # bash-era spec (kept for reference)
│   └── scratch-monkey.md      # this document
└── src/
    └── scratch_monkey/
        ├── __init__.py
        ├── config.py          # TOML read/write, InstanceConfig dataclass
        ├── instance.py        # Instance lifecycle (create, clone, delete, list)
        ├── container.py       # Podman subprocess wrapper (mockable)
        ├── overlay.py         # Overlay container logic
        ├── export.py          # Export command wrapper generation
        ├── shared.py          # Shared volume management
        ├── cli/
        │   ├── __init__.py
        │   └── main.py        # Click CLI — all user-facing commands
        └── gui/
            ├── __init__.py
            ├── main.py        # GUI entry point
            ├── models.py      # Atom-based observable models
            └── views/
                ├── main_window.enaml
                ├── instance_list.enaml
                └── instance_detail.enaml
tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_instance.py
    ├── test_container.py
    ├── test_overlay.py
    ├── test_shared.py
    └── test_export.py
```

---

## Module Responsibilities

### `config.py`

- Parse `scratch.toml` with `tomllib` — no more grep/sed
- `InstanceConfig` dataclass: all fields typed, with defaults
- `load(path)` / `save(path, config)` — save is atomic (write temp → rename)
- `validate_name(name)` — ensures valid instance name format

**InstanceConfig fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cmd` | `str` | `/bin/bash` | Command to run on entry |
| `wayland` | `bool` | `False` | Enable Wayland socket sharing |
| `ssh` | `bool` | `False` | Enable SSH agent sharing |
| `home` | `str` | `""` | Custom home directory override |
| `volumes` | `list[str]` | `[]` | Extra volume mounts |
| `env` | `list[str]` | `[]` | Extra environment variables |
| `shared` | `list[str]` | `[]` | Shared volume names |
| `overlay` | `bool` | `False` | Enable overlay mode |

### `container.py`

- `PodmanRunner` class: thin wrapper around `subprocess.run` calls
- Methods: `image_exists`, `container_exists`, `container_running`, `container_status`, `run`, `exec_in`, `exec_capture`, `start`, `stop`, `remove`, `rmi`, `build`, `run_daemon`
- All methods raise `PodmanError` on failure
- Fully mockable — no business logic here

### `instance.py`

- `Instance` dataclass (name, directory, config, home_dir)
- `create(name, instances_dir, base_image, project_dir)` → `Instance`
- `clone(source, dest, instances_dir)` → `Instance`
- `delete(name, instances_dir, runner)` — removes dir + image
- `list_all(instances_dir, runner)` → `list[InstanceInfo]`
- `skel_copy(instance)` → copies /etc/skel dotfiles
- `detect_base_image(instance_dir)` → last FROM line
- `is_fedora_based(instance_dir)` → bool

### `overlay.py`

- Manages the persistent daemon container `{name}-overlay`
- `ensure_running(instance, runner, image)` — create if missing, start if stopped
- **Fedora-only setup**: `useradd` + passwordless sudo via `_setup_fedora_user()`
- **Scratch instances**: user setup skipped entirely (host `/etc` is mounted r/o, user exists on host)
- `exec_shell(instance, runner, container_name, root, cmd)` — interactive exec
- `reset(instance, runner)` → removes daemon container

### `shared.py`

- `create_shared(name, instances_dir)` → `Path`
- `delete_shared(name, instances_dir)` — removes dir + removes from all instance configs atomically
- `add_to_instance(vol_name, instance, instances_dir)` → adds to config
- `remove_from_instance(vol_name, instance)` → removes from config
- `list_shared(instances_dir)` → `list[SharedVolumeInfo]`

### `export.py`

- `export_command(instance, cmd, bin_name, base_image, bin_dir)` → creates `~/.local/bin/<bin_name>`
- `unexport(bin_name, bin_dir)` — validates magic comment before deleting

The generated script:
1. If already inside the instance (`$SCRATCH_INSTANCE` matches), exec the command directly
2. If the overlay container is running, exec into it
3. Otherwise, `podman run --rm` with the instance image

### `cli/main.py`

Click application: `scratch-monkey <command>`

| Command | Description |
|---------|-------------|
| `create <name>` | Create a new instance (`--fedora`, `--skel`) |
| `clone <source> <dest>` | Clone an instance (fresh home) |
| `delete <name>` | Delete an instance (`--yes` to skip confirm) |
| `list` | List all instances with status |
| `skel <name>` | Copy /etc/skel files into home |
| `edit <name>` | Edit instance files (`--file config\|dockerfile\|env`) |
| `build` | Build the base image (`--fedora`) |
| `build-instance <name>` | Build an instance's Dockerfile |
| `run <name>` | Run an instance (`--root`, `--wayland`, `--ssh`, `--cmd`) |
| `enter <name>` | Interactive shell (`--root`) |
| `reset <name>` | Remove overlay container |
| `export <name> <cmd> [bin]` | Export a command to ~/.local/bin |
| `unexport <bin>` | Remove an exported command |
| `share create <name>` | Create a shared volume |
| `share delete <name>` | Delete a shared volume |
| `share add <vol> <instance>` | Add volume to instance config |
| `share remove <vol> <instance>` | Remove volume from instance config |
| `share list` | List all shared volumes |

Global options: `--instances-dir`, `--base-image`

### `gui/models.py`

- `InstanceModel(Atom)`: observable wrapper for a single instance
- `AppModel(Atom)`: root model with `instances`, `selected_instance`, `refresh()`
- Testable without Enaml views — pure Python/Atom

### `gui/views/`

- `main_window.enaml`: `ScratchMonkeyWindow` with toolbar, splitter, status bar
- `instance_list.enaml`: scrollable list with status indicators
- `instance_detail.enaml`: config editor + action buttons for selected instance

---

## Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = ["click>=8.0"]

[project.optional-dependencies]
gui = ["enaml[qt6-pyqt]>=0.19"]
dev = ["pytest", "pytest-mock", "ruff"]
```

---

## Testing Strategy

- **Unit tests**: all mocked at the `PodmanRunner` boundary — no real podman needed
- **Integration tests**: tagged `@pytest.mark.integration`, require real podman, skipped in CI by default
- **GUI tests**: test `models.py` only (pure Python/Atom); skip Enaml view rendering
- Coverage target: 80%+ on core modules

---

## Overlay Fix: Scratch vs. Fedora

`overlay.py::ensure_running()` calls `is_fedora_based()` which reads the Dockerfile's **last** FROM line:

- `FROM scratch_dev_fedora` → `is_fedora_based() = True` → run `useradd` + sudoers setup
- `FROM scratch_dev` (or anything non-fedora) → skip user setup entirely

This fixes the bug where `useradd` was run inside a scratch container whose `/etc` is the host's read-only filesystem.

---

## Dev Workflow (justfile)

```just
test:       uv run pytest
lint:       uv run ruff check src tests
fmt:        uv run ruff format src tests
install:    uv tool install --editable .
uninstall:  uv tool uninstall scratch-monkey
build:      uv build
```
