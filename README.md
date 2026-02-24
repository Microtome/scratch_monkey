# scratch_dev

A minimal container dev environment using Docker's `scratch` (empty) base image with host system directories bind-mounted in. Also supports a full `fedora:latest` base. Designed for rootless podman on Fedora/ostree systems.

## How it works

The scratch Dockerfile uses a multi-stage build to create filesystem symlinks (`/bin` -> `usr/bin`, etc.) that match the Fedora ostree layout, then copies them into a `scratch` image. At runtime, host directories like `/usr` and `/etc` are mounted in read-only, giving you a fully functional shell with no image bloat.

Alternatively, use the fedora base for a full OS environment with its own package manager — no host mounts needed.

Each scratch-dev **instance** is a named environment with its own home directory, customizable Dockerfile, and config file. Instances live under `$HOME/scratch-dev/`.

## Requirements

- [just](https://github.com/casey/just)
- podman (rootless)

## Quick start

```bash
# Build the base image
just build

# Create an instance
just create myproject

# Copy shell configs from /etc/skel
just skel myproject

# Run it
just enter myproject
```

### Fedora-based instance

```bash
just fedora=true build
just fedora=true create myproject
just enter myproject
```

## Instance management

```bash
# Create instances
just create myproject               # scratch base
just fedora=true create myproject   # fedora base

# Copy shell config files (.bashrc, etc.) from /etc/skel
just skel myproject

# List all instances
just list

# Clone an instance (copies config + Dockerfile, fresh home dir)
just clone myproject myproject-v2

# Edit instance files
just edit myproject                 # scratch.toml (default)
just edit myproject dockerfile      # Dockerfile
just edit myproject env             # .env secrets

# Delete an instance
just delete myproject
```

Each instance lives at `$HOME/scratch-dev/<name>/` with:
- `home/` — container home directory (mounted read-write)
- `Dockerfile` — customizable, extends the base image
- `scratch.toml` — instance configuration
- `.env` — environment variables / secrets (KEY=VALUE format)

## Running

```bash
# Interactive shell
just enter myproject

# Run a specific command
just run myproject "echo hello && whoami"

# Root shell (drops --userns=keep-id)
just enter-root myproject

# Override config flags from the CLI
just wayland=true ssh=true run myproject
```

## Feature flags

Flags can be set in `scratch.toml` per-instance or overridden on the CLI.

| Flag | Description |
|------|-------------|
| `wayland = true` | Mount Wayland socket, set `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR` |
| `ssh = true` | Forward `SSH_AUTH_SOCK` for SSH agent access |

Additional volumes (e.g., Homebrew) can be added via the `volumes` config in `scratch.toml`:

```toml
volumes = ["/home/linuxbrew/.linuxbrew:/home/linuxbrew/.linuxbrew:ro"]
```

## Customizing the Dockerfile

### Scratch instances

Instance Dockerfiles extend the base image. `RUN` does not work (no shell in the image) — use `COPY`/`ADD` or multi-stage builds:

```dockerfile
FROM golang:latest AS builder
RUN go install github.com/some/tool@latest

FROM scratch_dev
COPY --from=builder /go/bin/tool /usr/local/bin/tool
```

### Fedora instances

Full OS available — `RUN`, `COPY`, `ADD` all work:

```dockerfile
FROM scratch_dev_fedora
RUN dnf install -y git vim
```

Build and run:

```bash
just build-instance myproject
just run myproject
```

## What gets mounted

### Scratch instances

| Host path | Container path | Mode |
|---|---|---|
| `/usr` | `/usr` | read-only |
| `/etc` | `/etc` | read-only |
| `/var/usrlocal` | `/var/usrlocal`, `/usr/local` | read-only |
| `/var/opt` | `/var/opt` | read-only |
| Instance `home/` | same path | read-write |

### Fedora instances

| Host path | Container path | Mode |
|---|---|---|
| Instance `home/` | same path | read-write |

Fedora instances use their own filesystem — no host system mounts.

## All recipes

| Recipe | Description |
|--------|-------------|
| `just build` | Build the base image (`fedora=true` for fedora) |
| `just build-instance <name>` | Build an instance's Dockerfile |
| `just create <name>` | Create an instance (`fedora=true` for fedora) |
| `just clone <src> <dest>` | Clone an instance |
| `just delete <name>` | Delete an instance |
| `just edit <name> [file]` | Edit config (default), dockerfile, or env |
| `just skel <name>` | Copy /etc/skel configs into instance home |
| `just list` | List all instances |
| `just run <name> [cmd]` | Run an instance |
| `just enter <name>` | Interactive shell |
| `just enter-root <name>` | Interactive root shell |
| `just shell <name>` | Alias for run |
| `just clean` | Remove the base image |
| `just clean-instance <name>` | Remove an instance's image |
| `just status` | Show status |

## Notes

- Requires **podman** (uses `--userns=keep-id` for correct user mapping)
- SELinux labeling is disabled for the container (`--security-opt label=disable`)
- Host networking is enabled (`--network=host`)
- Use `enter-root` when you need root access (sudo doesn't work in user namespaces)
