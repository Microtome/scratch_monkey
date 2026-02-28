# scratch-monkey: How It Works

A deep dive into the architecture and features of scratch-monkey,
a Podman-based dev container manager for rootless Fedora/ostree systems.

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Base Image Architecture](#base-image-architecture)
- [Instance Lifecycle](#instance-lifecycle)
- [Container Runtime](#container-runtime)
- [Overlay Mode](#overlay-mode)
- [Shared Volumes](#shared-volumes)
- [Command Export](#command-export)
- [GPU and Device Passthrough](#gpu-and-device-passthrough)
- [Configuration Reference](#configuration-reference)
- [GUI](#gui)
- [CLI Reference](#cli-reference)

---

## Core Concepts

scratch-monkey manages **instances** — named dev environments backed by Podman
containers. Each instance has its own home directory, Dockerfile, config, and
optional persistent overlay.

```
                        scratch-monkey
                              |
              +---------------+---------------+
              |                               |
        scratch instances              fedora instances
              |                               |
     host /usr, /etc mounted        self-contained fedora:latest
     read-only into container       own package manager, own /usr
              |                               |
     near-zero image size             full OS in image
     instant startup                  slower build, more flexible
```

There are two fundamentally different base image types:

| | Scratch | Fedora |
|--|---------|--------|
| Base | Empty (`FROM scratch`) | `FROM fedora:latest` |
| Host mounts | `/usr`, `/etc`, `/var/usrlocal`, `/var/opt` (ro) | None |
| Package manager | Host's (via bind mount) | Container's own `dnf` |
| Image size | ~KB (just symlinks) | ~500MB+ |
| `RUN` in Dockerfile | No (no shell) | Yes |
| User setup in overlay | Skipped (host `/etc` has it) | `useradd` + sudoers created |
| Best for | Quick envs using host tools | Isolated envs needing own packages |

---

## Base Image Architecture

### Scratch base image

The scratch image is built with a multi-stage Dockerfile. A Fedora builder
creates a minimal rootfs with symlinks that match Fedora's ostree layout,
then copies it into an empty `FROM scratch` image.

```
+------------------------------------------+
|  Stage 1: fedora:latest (builder)        |
|                                          |
|  mkdir /rootfs/var/home                  |
|  mkdir /rootfs/var/opt                   |
|  mkdir /rootfs/var/usrlocal              |
|  mkdir /rootfs/usr                       |
|                                          |
|  Symlinks:                               |
|    /bin    -> usr/bin                     |
|    /sbin   -> usr/sbin                   |
|    /lib    -> usr/lib                    |
|    /lib64  -> usr/lib64                  |
|    /opt    -> var/opt                    |
|    /home   -> var/home                   |
+------------------------------------------+
                    |
                    v  COPY --from=builder
+------------------------------------------+
|  Stage 2: FROM scratch                   |
|                                          |
|  Contains only:                          |
|    /usr/          (empty dir)            |
|    /var/home/     (empty dir)            |
|    /var/opt/      (empty dir)            |
|    /var/usrlocal/ (empty dir)            |
|    + symlinks above                      |
|                                          |
|  No shell. No binaries. No OS.          |
+------------------------------------------+
```

At runtime, the host filesystem fills these empty directories:

```
Container view (scratch instance)
==================================

/usr/       <-- host /usr mounted read-only
/etc/       <-- host /etc mounted read-only
/usr/local/ <-- host /var/usrlocal mounted read-only
/var/opt/   <-- host /var/opt mounted read-only
/home/user/ <-- instance home/ mounted read-write
```

### Fedora base image

Just `FROM fedora:latest`. A complete OS. Only the instance home directory
is mounted from the host.

```
Container view (fedora instance)
==================================

/usr/       <-- from fedora:latest image layer
/etc/       <-- from fedora:latest image layer
/home/user/ <-- instance home/ mounted read-write
```

### Instance image layering

When you customize an instance's Dockerfile and run `build-instance`,
a new image layer is added on top of the base:

```
+-------------------------------+
|  Instance layer               |  <-- scratch-monkey build-instance myproject
|  (user's custom Dockerfile)   |
+-------------------------------+
|  Base image                   |  <-- scratch_dev or scratch_dev_fedora
|  (scratch or fedora)          |
+-------------------------------+
```

For scratch instances, the Dockerfile can't use `RUN` (no shell).
Use multi-stage builds to compile tools and `COPY` them in:

```dockerfile
FROM golang:latest AS builder
RUN go install github.com/some/tool@latest

FROM scratch_dev
COPY --from=builder /go/bin/tool /usr/local/bin/tool
```

For fedora instances, everything works normally:

```dockerfile
FROM scratch_dev_fedora
RUN dnf install -y git vim neovim
```

---

## Instance Lifecycle

### Directory structure

Each instance lives at `~/scratch-monkey/<name>/`:

```
~/scratch-monkey/
  myproject/
    home/           # Container home dir (mounted rw at /home/$USER)
    Dockerfile      # Extends base image, customizable
    scratch.toml    # Instance configuration
    .env            # Environment secrets (KEY=VALUE, one per line)
  another/
    home/
    Dockerfile
    scratch.toml
    .env
  .shared/          # Hidden dir for shared volumes
    comms/
    data/
```

### Create

```
scratch-monkey create myproject [--fedora] [--skel]
```

```
1. Validate name (alphanumeric start, then alphanum/underscore/dot/dash)
2. Create directory: ~/scratch-monkey/myproject/
3. Create subdirectory: home/
4. Copy scratch.toml.default -> scratch.toml
5. Generate Dockerfile (scratch or fedora template)
6. Create empty .env file
7. (--skel) Copy /etc/skel dotfiles into home/
```

### Clone

```
scratch-monkey clone myproject myproject-copy
```

```
1. Validate dest name
2. Create dest directory + home/
3. Copy source Dockerfile, scratch.toml, .env
4. Clear overlay_id in dest config (prevent shared overlay)
5. Tag source image for dest (if image exists)
6. home/ starts fresh (not copied)
```

### Delete

```
scratch-monkey delete myproject [--yes]
```

```
1. Remove overlay container (if any)
2. Remove podman image (if any)
3. Remove instance directory tree
```

### Rename

```
scratch-monkey rename old-name new-name
```

Renames the directory and re-tags the image. The overlay_id (if set)
is decoupled from the instance name, so overlays survive renames.

---

## Container Runtime

When you run `scratch-monkey enter myproject`, this is what happens:

```
+------------------------------------------------------------------+
|                    podman run arguments                           |
+------------------------------------------------------------------+
| --rm -it                          interactive, remove on exit    |
| --security-opt label=disable      disable SELinux labeling       |
| --network=host                    host networking                |
| --userns=keep-id                  rootless UID mapping           |
| --hostname myproject.myhostname   instance.host for prompts     |
+------------------------------------------------------------------+
| -e HOME=/home/user                                               |
| -e USER=user                                                     |
| -e SCRATCH_INSTANCE=myproject                                    |
| --workdir /home/user                                             |
+------------------------------------------------------------------+
| MOUNTS (scratch)           | MOUNTS (fedora)                    |
|  -v /usr:/usr:ro           |  (none — self-contained)           |
|  -v /etc:/etc:ro           |                                    |
|  -v /var/usrlocal:...:ro   |                                    |
|  -v /var/opt:/var/opt:ro   |                                    |
+------------------------------------------------------------------+
| -v ~/scratch-monkey/myproject/home:/home/user     (always)       |
| --env-file .env                                   (if exists)    |
+------------------------------------------------------------------+
| OPTIONAL (from scratch.toml)                                     |
|  -v wayland_socket    (wayland = true)                           |
|  -v SSH_AUTH_SOCK     (ssh = true)                               |
|  -v host:container    (volumes = [...])                          |
|  -e KEY=value         (env = [...])                              |
|  -v shared:/shared/x  (shared = [...])                           |
|  --device /dev/dri    (gpu = true)                               |
|  --device /dev/path   (devices = [...])                          |
+------------------------------------------------------------------+
```

---

## Overlay Mode

Overlay mode creates a persistent daemon container that survives between
sessions. Changes made inside the container (package installs, config edits
outside home/) persist without rebuilding the image.

### Without overlay (default)

```
scratch-monkey enter myproject

+-------------------+
| podman run --rm   |   Container is created, you work in it,
| -it myproject     |   it's destroyed when you exit.
| /bin/bash         |   Only home/ persists (bind mount).
+-------------------+
       |
       v
  [container destroyed on exit]
```

Every `enter` starts fresh from the image. Anything written outside
the home directory is lost.

### With overlay

```toml
# scratch.toml
overlay = true
```

```
First enter:

  scratch-monkey enter myproject

  1. No overlay container exists yet
  2. Create daemon: podman run -d --name sm-a1b2c3d4 ... sleep infinity
  3. (fedora only) Setup user: useradd, sudoers
  4. Exec into it: podman exec -it sm-a1b2c3d4 /bin/bash


Subsequent enters:

  scratch-monkey enter myproject

  1. Overlay container sm-a1b2c3d4 exists
  2. If stopped, start it
  3. Exec into it: podman exec -it sm-a1b2c3d4 /bin/bash


All sessions share the same container state.
Package installs, config changes outside home/ all persist.
```

```
                  Image layers                    Overlay container
               +------------------+          +------------------------+
               |  Instance layer  |   --->   |  Writable layer        |
               +------------------+   used   |  (dnf installs, etc.)  |
               |  Base image      |   as     |                        |
               +------------------+  base    +------------------------+
                                             |  Container filesystem  |
                                             |  persists across runs  |
                                             +------------------------+
```

### Overlay user setup (fedora only)

When a fedora overlay container starts for the first time, scratch-monkey
sets up the user inside it:

```
1. dnf install -y sudo          (if not present)
2. useradd -u <host_uid> -M -s /bin/bash <username>
3. echo "<user> ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/<user>
```

This is skipped for scratch instances because host `/etc` is bind-mounted
read-only — the host user and sudo config are already visible.

### Reset

```
scratch-monkey reset myproject
```

Removes the overlay container, discarding all changes outside home/.
Next `enter` creates a fresh overlay from the image.

### Overlay ID

Each overlay container gets a unique ID (e.g., `sm-a1b2c3d4`) stored in
`scratch.toml` as `overlay_id`. This decouples the container name from the
instance name, so renames don't break overlays. Cloning clears the
overlay_id to prevent two instances sharing one container.

---

## Shared Volumes

Shared volumes let multiple instances access the same host directory.
Useful for IPC via files, sockets, FIFOs, or shared databases.

```
~/scratch-monkey/.shared/
  comms/          <-- shared volume "comms"
  data/           <-- shared volume "data"
```

```
scratch-monkey share create comms
scratch-monkey share add comms agent1
scratch-monkey share add comms agent2
```

```
  agent1 container                    agent2 container
  +-------------------+              +-------------------+
  |                   |              |                   |
  | /shared/comms/ ------+     +------- /shared/comms/  |
  |                   |  |     |     |                   |
  +-------------------+  |     |     +-------------------+
                         v     v
                   +-------------------+
                   | ~/.../shared/comms |  (host directory)
                   +-------------------+
```

Mode control in `scratch.toml`:

```toml
shared = ["comms", "data:ro"]   # comms is rw, data is read-only
```

Deleting a shared volume automatically removes it from all instance configs.

---

## Command Export

Export makes a command from inside an instance available on your host PATH:

```
scratch-monkey export myproject /usr/bin/rg
```

This creates `~/.local/bin/rg` — a wrapper script with three execution paths:

```
~/.local/bin/rg is invoked
        |
        v
+-- Already inside myproject? --+
|   (SCRATCH_INSTANCE == name)  |
|           |                   |
|     yes   |             no    |
|     exec  |                   |
|     /usr/bin/rg         +-- Overlay running? --+
|     directly            |         |            |
|                   yes   |            no        |
|                   podman exec        podman run --rm
|                   into overlay       one-shot container
|                   run /usr/bin/rg    run /usr/bin/rg
+-----------------------------------------------+
```

Remove with `scratch-monkey unexport rg`.

---

## GPU and Device Passthrough

### GPU auto-detection

When `gpu = true` in `scratch.toml`, scratch-monkey scans for:

| Device | Purpose |
|--------|---------|
| `/dev/dri` | DRM (Intel, AMD, generic GPU) |
| `/dev/kfd` | AMD ROCm compute |
| `/dev/nvidia*` | NVIDIA GPUs |

Each detected device is passed with `--device`.

### Extra devices

For other hardware (webcams, USB devices, etc.):

```toml
devices = ["/dev/video0", "/dev/bus/usb"]
```

---

## Configuration Reference

All fields in `scratch.toml` are optional.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cmd` | string | `/bin/bash` | Shell command to run on entry |
| `wayland` | bool | `false` | Forward Wayland display socket |
| `ssh` | bool | `false` | Forward SSH agent socket |
| `home` | string | `""` | Override home dir (empty = instance `home/`) |
| `overlay` | bool | `false` | Enable persistent overlay container |
| `gpu` | bool | `false` | Auto-detect and pass through GPU devices |
| `volumes` | list | `[]` | Extra bind mounts (`host:container[:mode]`) |
| `env` | list | `[]` | Extra environment variables (`KEY=value`) |
| `shared` | list | `[]` | Shared volume names (`name` or `name:ro`) |
| `devices` | list | `[]` | Extra device paths to pass through |
| `overlay_id` | string | `""` | Auto-generated overlay container ID |

### Environment inside the container

These are always set:

| Variable | Value |
|----------|-------|
| `HOME` | `/home/$USER` (or `/root` with `--root`) |
| `USER` | Host username |
| `SCRATCH_INSTANCE` | Instance name |

Conditionally set:

| Variable | When |
|----------|------|
| `WAYLAND_DISPLAY` | `wayland = true` |
| `XDG_RUNTIME_DIR` | `wayland = true` |
| `SSH_AUTH_SOCK` | `ssh = true` |

Plus any variables from `.env` and the `env` config list.

---

## GUI

Install with GUI dependencies:

```bash
uv tool install --editable ".[gui]"
scratch-monkey gui
```

The GUI provides a graphical interface to all instance management features.

```
+------------------------------------------------------------------+
| scratch-monkey                              [New Instance] [Refresh] |
+------------------------------------------------------------------+
|                    |                                              |
|  Instance List     |  Instance Detail                            |
|                    |                                              |
|  * fedora-dev  [C][R][X] |  fedora-dev                          |
|    myproject   [C][R][X] |  Path: ~/scratch-monkey/fedora-dev   |
|    tools       [C][R][X] |  Base: scratch_dev_fedora             |
|                    |                                              |
|                    |  Actions                                    |
|                    |  [Enter] [Enter as Root] [Build] [Reset]    |
|                    |  [Export Cmd] [Edit Dockerfile] [Edit .env]  |
|                    |  [Edit Config]                               |
|                    |                                              |
|                    |  [====== Save Config ======] [Cancel Changes]|
|                    |                                              |
|                    |  Configuration                               |
|                    |  Command: [/bin/bash           ]             |
|                    |  Home:    [/home/dev            ]            |
|                    |  [ ] Wayland  [ ] SSH Agent                  |
|                    |  [ ] Overlay  [ ] GPU Passthrough             |
|                    |                                              |
|                    |  Volume Mounts                               |
|                    |  [host path] [container path] [rw v] [X]    |
|                    |  [+ Add Volume Mount]                        |
|                    |                                              |
|                    |  Environment Variables                       |
|                    |  [KEY] [value                        ] [X]   |
|                    |  [+ Add Environment Variable]                |
|                    |                                              |
|                    |  Devices                                     |
|                    |  [/dev/video0                        ] [X]   |
|                    |  [+ Add Device]                              |
|                    |                                              |
|                    |  Shared Volumes                              |
|                    |  [x] comms [rw v]                           |
|                    |  [ ] data  [rw v]                           |
|                    |  [+ New Shared Volume]                       |
|                    |                                              |
|  [+ New Instance]  |                                              |
+------------------------------------------------------------------+
| Loaded 3 instance(s)                                             |
+------------------------------------------------------------------+
```

### Key features

- **Instance list**: Status indicators (running/built/no image), base type (F for fedora),
  clone/rename/delete buttons per instance
- **Config editing**: All scratch.toml fields editable in-place, dirty tracking
  with save/revert, orange highlight on unsaved changes
- **Actions**: Enter, build, reset overlay, export commands, edit files in terminal
- **Edit Config**: Opens scratch.toml in `$VISUAL`/`$EDITOR`, auto-reloads on close
- **Create dialog**: Name, fedora toggle, skel toggle, full config editor
- **Shared volumes**: Toggle per-instance, create new volumes inline

---

## CLI Reference

### Global options

```
scratch-monkey [--instances-dir DIR] [--base-image IMAGE] COMMAND
```

| Option | Default | Description |
|--------|---------|-------------|
| `--instances-dir` | `~/scratch-monkey` | Where instances are stored |
| `--base-image` | `scratch_dev` | Default base image for new instances |

### Commands

| Command | Description |
|---------|-------------|
| `create <name> [--fedora] [--skel]` | Create a new instance |
| `clone <source> <dest>` | Clone instance (fresh home) |
| `delete <name> [--yes]` | Delete instance, image, and overlay |
| `rename <old> <new>` | Rename an instance |
| `list` | List all instances with status |
| `skel <name>` | Copy /etc/skel dotfiles into home |
| `edit <name> [--file config\|dockerfile\|env]` | Edit instance files |
| `build [--fedora] [--yes]` | Build a base image |
| `build-instance <name>` | Build instance Dockerfile (auto-builds base) |
| `enter <name> [--root]` | Interactive shell |
| `run <name> [--root] [--wayland] [--ssh] [--cmd CMD]` | Run with overrides |
| `reset <name> [--yes]` | Remove overlay container |
| `export <name> <cmd> [bin]` | Export command to ~/.local/bin |
| `unexport <bin>` | Remove exported command |
| `share create <name>` | Create a shared volume |
| `share delete <name> [--yes]` | Delete shared volume (cleans all configs) |
| `share add <vol> <instance>` | Add volume to instance |
| `share remove <vol> <instance>` | Remove volume from instance |
| `share list` | List volumes and which instances use them |
| `gui` | Launch graphical interface |
