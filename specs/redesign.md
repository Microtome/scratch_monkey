# scratch_dev Redesign Spec

## Overview

Port `run.sh` to a `justfile` with an instance-based workflow. Each scratch-dev instance is a named environment with its own home directory, Dockerfile, config file, and optional secrets. Instances live under `$HOME/scratch-dev/`. Supports both a `scratch` base image (host mounts) and a `fedora:latest` base (self-contained). Targeting rootless podman on Fedora/ostree. No Python; large recipes are extracted to `scripts/`.

## Directory Layout

### Project (this repo)

```
scratch_dev/                    # This git repo
  justfile                      # Primary interface — all recipes
  Dockerfile                    # Base scratch image
  Dockerfile.fedora             # Base fedora image
  scratch.toml.default          # Template config with all options commented out
  scripts/
    create.sh                   # Instance creation logic
    run.sh                      # Container launch logic
    list.sh                     # Instance listing
    skel.sh                     # Skeleton file copying
  specs/
    redesign.md                 # This document
  README.md                     # Usage docs
```

### User instances (`$HOME/scratch-dev/`)

```
$HOME/scratch-dev/
  .shared/                      # Shared volumes (created via: just share-create <name>)
    comms/                      # Mounted at /shared/comms inside containers
  myproject/                    # Instance created via: just create myproject
    home/                       # Container home directory (mounted rw)
    Dockerfile                  # Customizable, FROM scratch_dev or scratch_dev_fedora
    scratch.toml                # Instance config (all options, defaults commented out)
    .env                        # Environment variables / secrets (KEY=VALUE format)
  work-env/                     # Another instance
    home/
    Dockerfile
    scratch.toml
    .env
```

## Instance Config: `scratch.toml`

Generated from `scratch.toml.default` when an instance is created. All values are commented out, showing defaults:

```toml
# scratch-dev instance configuration

# Command to run on entry
# cmd = "/bin/bash"

# Sharing options
# wayland = false
# ssh = false

# Custom home directory (overrides the instance home/ dir)
# home = ""

# Extra volume mounts (host:container:mode)
# volumes = []
#
# Example: mount Homebrew (Linuxbrew) read-only
# volumes = ["/home/linuxbrew/.linuxbrew:/home/linuxbrew/.linuxbrew:ro"]

# Extra environment variables
# env = []

# Shared volumes (created via: just share-create <name>)
# Mounted at /shared/<name> inside the container
# shared = []
```

When a value is uncommented, it overrides the default. The run script parses this with simple grep/sed (TOML subset — flat key/value only, no nested tables).

## Justfile Variables (Flags)

All passed as `just var=value recipe`:

| Variable | Default | Description |
|----------|---------|-------------|
| `fedora` | `""` | Set to `true` to use the fedora base image |
| `skel` | `""` | Set to `true` to copy /etc/skel configs on create |
| `root` | `""` | Set to `true` to run as root (drops `--userns=keep-id`) |
| `wayland` | `""` | Set to `true` to override wayland config |
| `ssh` | `""` | Set to `true` to override ssh config |
| `cmd` | `""` | Override the command to run |

## Justfile Recipes

### Instance Management

| Recipe | Purpose |
|--------|---------|
| `create name` | Create a new instance (`fedora=true` for fedora base, `skel=true` to copy shell configs) |
| `clone source dest` | Clone an existing instance (copies Dockerfile + scratch.toml + .env, creates fresh home/) |
| `delete name` | Delete an instance (prompts for confirmation, removes dir + image) |
| `skel name` | Copy /etc/skel bash configs into instance home |
| `edit name [file]` | Edit instance file: `config` (default), `dockerfile`, or `env` |

### Info

| Recipe | Purpose |
|--------|---------|
| `list` | List all instances with status |

### Build

| Recipe | Purpose |
|--------|---------|
| `build` | Build the base image (`fedora=true` for fedora) |
| `build-instance name` | Build an instance's Dockerfile (auto-detects base, tagged as `name`) |

### Run

| Recipe | Purpose |
|--------|---------|
| `run name [args]` | Launch a container for the named instance |
| `shell name [args]` | Alias for `run` |
| `enter name` | Interactive shell (`root=true` for root) |

### Shared Volumes

| Recipe | Purpose |
|--------|---------|
| `share-create name` | Create a shared volume at `$HOME/scratch-dev/.shared/<name>/` |
| `share-delete name` | Delete a shared volume (prompts for confirmation) |
| `share-add name instance` | Add a shared volume to an instance's `shared` list in scratch.toml |
| `share-remove name instance` | Remove a shared volume from an instance's `shared` list |
| `share-list` | List all shared volumes and which instances use them |

### Maintenance

| Recipe | Purpose |
|--------|---------|
| `clean` | Remove the base image |
| `clean-instance name` | Remove an instance's image |
| `status` | Show base image info and all instances |

## Usage Examples

```bash
# Build the base image (auto-builds on first run if missing)
just build

# Build the fedora base image
just fedora=true build

# Create a new instance (scratch base, with shell configs)
just skel=true create myproject

# Create a fedora-based instance
just skel=true fedora=true create myproject

# Edit instance files
just edit myproject                 # scratch.toml (default)
just edit myproject dockerfile      # Dockerfile
just edit myproject env             # .env secrets

# Build and run the instance
just build-instance myproject
just run myproject

# Interactive shell
just enter myproject

# Root shell
just root=true enter myproject

# Run with flag overrides
just wayland=true ssh=true run myproject

# Run a specific command
just run myproject "echo hello && whoami"

# Copy skeleton configs to existing instance
just skel myproject

# Clone an instance
just clone myproject myproject-v2

# List all instances
just list

# Delete an instance
just delete myproject
```

## Instance Lifecycle

### `just create myproject`

1. Creates `$HOME/scratch-dev/myproject/`
2. Creates `$HOME/scratch-dev/myproject/home/`
3. Copies `scratch.toml.default` → `$HOME/scratch-dev/myproject/scratch.toml`
4. Generates `$HOME/scratch-dev/myproject/Dockerfile`:
   - Scratch: `FROM scratch_dev` with note that RUN does not work
   - Fedora: `FROM scratch_dev_fedora` with note that RUN/COPY/ADD all work
5. Creates empty `.env` file
6. Prints instructions for next steps (using `just edit` and `just enter`)

If `skel=true`, also copies /etc/skel dotfiles into the home directory.

### `just clone myproject myproject-v2`

1. Verifies source instance exists
2. Creates `$HOME/scratch-dev/myproject-v2/`
3. Creates `$HOME/scratch-dev/myproject-v2/home/` (fresh, empty)
4. Copies `Dockerfile`, `scratch.toml`, and `.env` from source
5. Does **not** copy the source home directory (clean slate)

### `just delete myproject`

1. Prompts for confirmation
2. Removes the podman image tagged `myproject` (if it exists)
3. Removes `$HOME/scratch-dev/myproject/` recursively

### `just list`

Shows all instances with status:

```
INSTANCE             IMAGE BUILT     DIRECTORY                                CONFIG
myproject            yes             /var/home/user/scratch-dev/myproject     wayland=true, ssh=true
work-env             no              /var/home/user/scratch-dev/work-env      (defaults)
```

## Feature Flags

Flags can be set in `scratch.toml` per-instance, or overridden on the CLI via `just key=value run name`.

### Wayland Socket Sharing (`wayland = true`)

Mounts the Wayland compositor socket so GUI applications can render.

**Mounts:**
- `/run/user/<UID>/wayland-0` → same path in container

**Environment:**
- `WAYLAND_DISPLAY=wayland-0`
- `XDG_RUNTIME_DIR=/run/user/<UID>`

Warns and skips if the socket is not found.

### SSH Agent Sharing (`ssh = true`)

Forwards the host SSH agent so `ssh`, `git` over SSH, etc. work with the host's loaded keys.

**Mounts:**
- `$SSH_AUTH_SOCK` → same path in container

**Environment:**
- `SSH_AUTH_SOCK=<same value as host>`

Warns and skips if `SSH_AUTH_SOCK` is not set or the socket is missing.

### Homebrew (via volumes config)

Homebrew is not a built-in flag. Instead, use the `volumes` config in `scratch.toml`:

```toml
volumes = ["/home/linuxbrew/.linuxbrew:/home/linuxbrew/.linuxbrew:ro"]
```

Users configure their shell rc files to add brew to PATH.

## Secrets: `.env` File

Each instance has a `.env` file for environment variables and secrets (KEY=VALUE format, one per line). Loaded via `podman run --env-file`. This keeps secrets out of the Dockerfile and scratch.toml.

## Root Access

Rootless podman uses `--userns=keep-id` for correct user mapping, which means sudo/setuid doesn't work. Use `just root=true enter myproject` to drop `--userns=keep-id` and run as root.

## Dockerfile Customization

### Base Images

- **`scratch_dev`**: Empty `scratch` image with Fedora ostree symlinks (`/bin` → `usr/bin`, etc.) and empty mount-point directories. Host provides all executables via bind mounts at runtime.
- **`scratch_dev_fedora`**: Full `fedora:latest` image. Self-contained, no host mounts needed.

### Scratch Instance Dockerfiles

`RUN` does **not** work (no shell in the image). Use `COPY`/`ADD` or multi-stage builds:

```dockerfile
FROM golang:latest AS builder
RUN go install github.com/some/tool@latest

FROM scratch_dev
COPY --from=builder /go/bin/tool /usr/local/bin/tool
```

### Fedora Instance Dockerfiles

Full OS available — `RUN`, `COPY`, `ADD` all work:

```dockerfile
FROM scratch_dev_fedora
RUN dnf install -y git vim
```

Build with `just build-instance myproject`, then run normally.

## Shared Volumes

Shared volumes enable communication between scratch-dev instances via a shared filesystem directory. Since containers already use `--network=host`, shared volumes complement that with a simple, reliable IPC channel for files, unix sockets, FIFOs, or databases.

### Directory

Shared volumes live at `$HOME/scratch-dev/.shared/<name>/`. At run time, each name in an instance's `shared` config resolves to a mount at `/shared/<name>` inside the container.

### Config

The `shared` key in `scratch.toml` lists shared volume names:

```toml
shared = ["comms", "data"]
```

### Workflow

```bash
just share-create comms              # creates $HOME/scratch-dev/.shared/comms/
just share-add comms agent1          # adds "comms" to agent1's scratch.toml
just share-add comms agent2          # adds "comms" to agent2's scratch.toml
just enter agent1                    # /shared/comms/ is mounted rw
just enter agent2                    # /shared/comms/ is mounted rw — same host dir
just share-list                      # shows all shared volumes
just share-remove comms agent1       # removes "comms" from agent1's config
just share-delete comms              # deletes the shared directory
```

### Run logic

In `scripts/run.sh`, after parsing extra volumes, the `shared` key is parsed using the same grep/sed pattern. For each name, a `-v "$instances_dir/.shared/$name:/shared/$name"` mount is added. Missing shared directories emit a warning and are skipped.

## Core Run Logic (`scripts/run.sh`)

The run script for a named instance:

1. Reads `$HOME/scratch-dev/<name>/scratch.toml` for config values
2. Applies CLI overrides (wayland, ssh, cmd)
3. Determines the image: if instance image `<name>` exists, use it; otherwise detect base from Dockerfile FROM line, fall back to `scratch_dev`
4. Auto-builds base image if missing
5. Detects if instance is fedora-based (from Dockerfile FROM line)
6. Assembles podman arguments

**Always applied:**
- `--rm -it`
- `--security-opt label=disable` (SELinux bypass for host mounts)
- `--network=host`
- `-e HOME=<home>`
- Home directory mounted rw

**Scratch instances only (skipped for fedora):**
- Host mounts: `/usr`, `/etc`, `/var/usrlocal`, `/var/opt`, `/usr/local` (all `:ro`)

**Unless `root=true`:**
- `--userns=keep-id` (correct user mapping in rootless podman)

**Conditionally applied based on flags:**
- Wayland mounts + env vars
- SSH socket mount + env var
- `.env` file via `--env-file`
- Extra volumes from `scratch.toml`
- Shared volumes from `scratch.toml` (mounted at `/shared/<name>`)
- Extra env vars from `scratch.toml`

## Config Parsing

The TOML config is a flat key/value format (no nested tables). Parsing is done with grep/sed in bash:

```bash
get() {
    local key="$1" default="$2" override="$3"
    if [[ -n "$override" ]]; then
        echo "$override"
        return
    fi
    local val
    val=$(grep -E "^${key}\s*=" "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '"' | tr -d "'" | xargs)
    echo "${val:-$default}"
}
```

Commented lines (`# key = value`) are ignored by the `^key` anchor. CLI overrides take precedence. This handles the simple subset we need without requiring a TOML parser.

## Implementation Order

1. Create `specs/redesign.md` (this document)
2. Create `scratch.toml.default`
3. Create `justfile` with all recipes
4. Create `scripts/` with extracted bash scripts
5. Update `README.md` for new usage
6. Remove old `run.sh`
