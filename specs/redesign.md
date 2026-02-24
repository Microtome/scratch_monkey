# scratch_dev Redesign Spec

## Overview

Port `run.sh` to a `justfile` with an instance-based workflow. Each scratch-dev instance is a named environment with its own home directory, Dockerfile, and config file. All instances live under `$HOME/scratch-dev/`. Targeting rootless podman on Fedora/ostree. No Python; all logic is inline bash within justfile recipes.

## Directory Layout

### Project (this repo)

```
scratch_dev/                    # This git repo
  justfile                      # Primary interface — all recipes
  Dockerfile                    # Base scratch image
  scratch.toml.default          # Template config with all options commented out
  specs/
    redesign.md                 # This document
  README.md                     # Updated usage docs
```

### User instances (`$HOME/scratch-dev/`)

```
$HOME/scratch-dev/
  myproject/                    # Instance created via: just create myproject
    home/                       # Container home directory (mounted rw)
    Dockerfile                  # Customizable, FROM scratch_dev
    scratch.toml                # Instance config (all options, defaults commented out)
  work-env/                     # Another instance
    home/
    Dockerfile
    scratch.toml
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
# brew = false

# Custom home directory (overrides the instance home/ dir)
# home = ""

# Extra volume mounts (host:container:mode)
# volumes = []

# Extra environment variables
# env = []
```

When a value is uncommented, it overrides the default. The justfile parses this with simple grep/sed (TOML subset — flat key/value only, no nested tables).

## Justfile Recipes

### Instance Management

| Recipe | Purpose |
|--------|---------|
| `create name` | Create a new instance (dir, home/, Dockerfile, scratch.toml) |
| `clone source dest` | Clone an existing instance (copies Dockerfile + scratch.toml, creates fresh home/) |
| `delete name` | Delete an instance (prompts for confirmation, removes dir + image) |
| `list` | List all instances and their status |

### Build & Run

| Recipe | Purpose |
|--------|---------|
| `build` | Build the base `scratch_dev` image |
| `build-instance name` | Build an instance's Dockerfile (tagged as `name`) |
| `run name` | Launch a container for the named instance |
| `shell name` | Alias for `run` with `/bin/bash` |

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

# Create a new instance
just create myproject

# Customize the instance (edit Dockerfile and/or config)
$EDITOR ~/scratch-dev/myproject/Dockerfile
$EDITOR ~/scratch-dev/myproject/scratch.toml

# Build and run the instance
just build-instance myproject
just run myproject

# Run with flag overrides (override config values from CLI)
just run myproject wayland=true ssh=true

# Clone an instance
just clone myproject myproject-v2

# List all instances
just list

# Delete an instance
just delete myproject

# Run a specific command
just run myproject -- -c "echo hello"
```

## Instance Lifecycle

### `just create myproject`

1. Creates `$HOME/scratch-dev/myproject/`
2. Creates `$HOME/scratch-dev/myproject/home/`
3. Copies `scratch.toml.default` → `$HOME/scratch-dev/myproject/scratch.toml`
4. Generates `$HOME/scratch-dev/myproject/Dockerfile`:
   ```dockerfile
   FROM scratch_dev
   # Add your customizations here.
   # COPY and ADD work. RUN does not (no shell in image).
   # Use multi-stage builds to pull binaries from other images.
   ```
5. Prints instructions for next steps

### `just clone myproject myproject-v2`

1. Verifies source instance exists
2. Creates `$HOME/scratch-dev/myproject-v2/`
3. Creates `$HOME/scratch-dev/myproject-v2/home/` (fresh, empty)
4. Copies `Dockerfile` and `scratch.toml` from source
5. Does **not** copy the source home directory (clean slate)

### `just delete myproject`

1. Prompts for confirmation
2. Removes the podman image tagged `myproject` (if it exists)
3. Removes `$HOME/scratch-dev/myproject/` recursively

### `just list`

Shows all instances with status:

```
INSTANCE        IMAGE BUILT     CONFIG
myproject       yes             wayland=true, ssh=true
work-env        no              (defaults)
```

## Feature Flags

Flags can be set in `scratch.toml` per-instance, or overridden on the CLI via `just run name key=value`.

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

### Homebrew Sharing (`brew = true`)

Mounts the host's Homebrew (Linuxbrew) installation read-only.

**Mounts:**
- `/home/linuxbrew/.linuxbrew` or `~/.linuxbrew` → same path, read-only

**Environment:** None. Users configure their shell rc files to add brew to PATH:
```bash
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
```

Detection order: `/home/linuxbrew/.linuxbrew` first, then `$HOME/.linuxbrew`. Warns if neither found.

## Dockerfile Customization

### Base Image

The `Dockerfile` in this repo builds the `scratch_dev` base image — a `scratch` image with only filesystem symlinks (`/bin` → `usr/bin`, etc.) and empty mount-point directories.

### Instance Dockerfiles

Each instance gets its own Dockerfile that starts with `FROM scratch_dev`. Users can add layers:

- `COPY` / `ADD` static files, configs, binaries
- Multi-stage builds to pull binaries from other images
- Set `ENV`, `WORKDIR`, `ENTRYPOINT`, `CMD`

`RUN` does **not** work (no shell in the image). This is by design — the host provides all executables via bind mounts at runtime.

### Example: Adding a Go tool

```dockerfile
FROM golang:latest AS builder
RUN go install github.com/some/tool@latest

FROM scratch_dev
COPY --from=builder /go/bin/tool /usr/local/bin/tool
```

## Core `run` Recipe Design

The `run` recipe for a named instance:

1. Reads `$HOME/scratch-dev/<name>/scratch.toml` for config values
2. Applies CLI overrides (e.g., `wayland=true`)
3. Determines the image: if instance image `<name>` exists, use it; otherwise fall back to `scratch_dev` base
4. Auto-builds base image if missing
5. Assembles podman arguments

**Always applied:**
- `--rm -it`
- `--userns=keep-id` (correct user mapping in rootless podman)
- `--security-opt label=disable` (SELinux bypass for host mounts)
- `--network=host`
- `-e HOME=<home>`
- Host mounts: `/usr`, `/etc`, `/var/usrlocal`, `/var/opt`, `/usr/local` (all `:ro`)
- Home directory: `$HOME/scratch-dev/<name>/home` mounted rw (or custom `home` from config)

**Conditionally applied based on flags:**
- Wayland mounts + env vars
- SSH socket mount + env var
- Homebrew directory mount

## Config Parsing

The TOML config is a flat key/value format (no nested tables). Parsing is done with grep/sed in bash:

```bash
get_config() {
    local file="$1" key="$2" default="$3"
    local val
    val=$(grep -E "^${key}\s*=" "$file" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '"' | tr -d "'" | xargs)
    echo "${val:-$default}"
}
```

Commented lines (`# key = value`) are ignored by the `^key` anchor. This handles the simple subset we need without requiring a TOML parser.

## Implementation Order

1. Create `specs/redesign.md` (this document)
2. Create `scratch.toml.default`
3. Create `justfile` with all recipes
4. Update `README.md` for new usage
5. Remove `run.sh`
