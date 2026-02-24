# scratch_dev

A minimal container dev environment using Docker's `scratch` (empty) base image with host system directories bind-mounted in. Designed for rootless podman on Fedora/ostree systems.

## How it works

The Dockerfile uses a multi-stage build to create filesystem symlinks (`/bin` -> `usr/bin`, etc.) that match the Fedora ostree layout, then copies them into a `scratch` image. At runtime, host directories like `/usr` and `/etc` are mounted in read-only, giving you a fully functional shell with no image bloat.

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

# Run it
just run myproject
```

## Instance management

```bash
# Create a new instance
just create myproject

# List all instances
just list

# Clone an instance (copies config + Dockerfile, fresh home dir)
just clone myproject myproject-v2

# Delete an instance
just delete myproject
```

Each instance lives at `$HOME/scratch-dev/<name>/` with:
- `home/` — container home directory (mounted read-write)
- `Dockerfile` — customizable, extends the base `scratch_dev` image
- `scratch.toml` — instance configuration

## Running

```bash
# Interactive shell
just run myproject

# Run a specific command
just run myproject "echo hello && whoami"

# Override config flags from the CLI
just run myproject wayland=true ssh=true
```

## Feature flags

Flags can be set in `scratch.toml` per-instance or overridden on the CLI.

| Flag | Description |
|------|-------------|
| `wayland = true` | Mount Wayland socket, set `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR` |
| `ssh = true` | Forward `SSH_AUTH_SOCK` for SSH agent access |
| `brew = true` | Mount Homebrew installation read-only |

## Customizing the Dockerfile

Instance Dockerfiles extend the base image:

```dockerfile
FROM scratch_dev
COPY ./my-tool /usr/local/bin/my-tool
```

Multi-stage builds work for pulling binaries from other images:

```dockerfile
FROM golang:latest AS builder
RUN go install github.com/some/tool@latest

FROM scratch_dev
COPY --from=builder /go/bin/tool /usr/local/bin/tool
```

Build and run:

```bash
just build-instance myproject
just run myproject
```

Note: `RUN` does not work in instance Dockerfiles (no shell in the image). Use `COPY`/`ADD` or multi-stage builds.

## What gets mounted

| Host path | Container path | Mode |
|---|---|---|
| `/usr` | `/usr` | read-only |
| `/etc` | `/etc` | read-only |
| `/var/usrlocal` | `/var/usrlocal`, `/usr/local` | read-only |
| `/var/opt` | `/var/opt` | read-only |
| Instance `home/` | same path | read-write |

## All recipes

| Recipe | Description |
|--------|-------------|
| `just build` | Build the base image |
| `just build-instance <name>` | Build an instance's Dockerfile |
| `just create <name>` | Create a new instance |
| `just clone <src> <dest>` | Clone an instance |
| `just delete <name>` | Delete an instance |
| `just list` | List all instances |
| `just run <name>` | Run an instance |
| `just shell <name>` | Alias for run |
| `just clean` | Remove the base image |
| `just clean-instance <name>` | Remove an instance's image |
| `just status` | Show status |

## Notes

- Requires **podman** (uses `--userns=keep-id` for correct user mapping)
- SELinux labeling is disabled for the container (`--security-opt label=disable`)
- Host networking is enabled (`--network=host`)
