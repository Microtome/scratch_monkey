# scratch_dev

A minimal container dev environment using Docker's `scratch` (empty) base image with host system directories bind-mounted in. Designed for rootless podman on Fedora/ostree systems.

## How it works

The Dockerfile uses a multi-stage build to create filesystem symlinks (`/bin` -> `usr/bin`, etc.) that match the Fedora ostree layout, then copies them into a `scratch` image. At runtime, host directories like `/usr`, `/etc`, and your home directory are mounted in, giving you a fully functional shell with no image bloat.

## Usage

```bash
# Interactive shell
./run.sh --home /var/home/youruser

# Run a command
./run.sh --home /var/home/youruser -- -c "echo hello"
```

The image is built automatically on first run.

To rebuild manually:

```bash
podman build -t scratch_dev-app .
```

## What gets mounted

| Host path | Container path | Mode |
|---|---|---|
| `/usr` | `/usr` | read-only |
| `/etc` | `/etc` | read-only |
| `/var/usrlocal` | `/var/usrlocal`, `/usr/local` | read-only |
| `/var/opt` | `/var/opt` | read-only |
| `--home` dir | same path | read-write |

## Notes

- Requires **podman** (uses `--userns=keep-id` for correct user mapping)
- SELinux labeling is disabled for the container (`--security-opt label=disable`)
- Host networking is enabled (`--network=host`)
