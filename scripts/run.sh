#!/usr/bin/env bash
set -euo pipefail

# Usage: run.sh <instances_dir> <base_image> <project_dir> <name> <root> <wayland> <ssh> <cmd> [args...]
instances_dir="$1"
base_image="$2"
project_dir="$3"
name="$4"
opt_root="$5"
opt_wayland="$6"
opt_ssh="$7"
opt_cmd="$8"
shift 8

dir="$instances_dir/$name"
conf="$dir/scratch.toml"
if [[ ! -d "$dir" ]]; then
    echo "Error: instance '$name' not found at $dir"
    exit 1
fi

# Read config with CLI overrides
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

cfg_cmd=$(get "cmd" "/bin/bash" "$opt_cmd")
cfg_wayland=$(get "wayland" "false" "$opt_wayland")
cfg_ssh=$(get "ssh" "false" "$opt_ssh")
cfg_home=$(get "home" "" "")

# Determine home directory
if [[ -n "$cfg_home" ]]; then
    home_dir="$cfg_home"
else
    home_dir="$dir/home"
fi

# Create home dir if missing
if [[ ! -d "$home_dir" ]]; then
    read -rp "'$home_dir' does not exist. Create it? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        mkdir -p "$home_dir"
    else
        exit 1
    fi
fi

# Determine image: use instance image if built, otherwise base
if podman image exists "$name" 2>/dev/null; then
    run_image="$name"
else
    # Check which base the instance Dockerfile uses
    instance_base=$(grep -E '^FROM\s+' "$dir/Dockerfile" 2>/dev/null | head -1 | awk '{print $2}')
    run_image="${instance_base:-$base_image}"
    # Ensure base image exists
    if ! podman image exists "$run_image"; then
        echo "Base image '$run_image' not found, building..."
        if [[ "$run_image" == *fedora* ]]; then
            podman build -t "$run_image" -f "$project_dir/Dockerfile.fedora" "$project_dir"
        else
            podman build -t "$run_image" "$project_dir"
        fi
    fi
fi

# Detect if instance is fedora-based
is_fedora=false
instance_base=$(grep -E '^FROM\s+' "$dir/Dockerfile" 2>/dev/null | tail -1 | awk '{print $2}')
[[ "$instance_base" == *fedora* ]] && is_fedora=true

# Determine the home path inside the container
if [[ "$opt_root" == "true" ]]; then
    container_home="/root"
else
    container_home="/home/$USER"
fi

# Base podman arguments
podman_args=(
    --rm -it
    --security-opt label=disable
    --network=host
    --hostname "$name.$(hostname -s)"
    --workdir "$container_home"
    -e "HOME=$container_home"
    -e "USER=$USER"
    -v "$home_dir":"$container_home"
)

# Host system mounts (scratch only — fedora has its own)
if [[ "$is_fedora" == "false" ]]; then
    podman_args+=(
        -v /usr:/usr:ro
        -v /etc:/etc:ro
        -v /var/usrlocal:/var/usrlocal:ro
        -v /var/opt:/var/opt:ro
        -v /var/usrlocal:/usr/local:ro
    )
fi

# Run as current user unless root mode requested
if [[ "$opt_root" != "true" ]]; then
    podman_args+=(--userns=keep-id)
fi

# Wayland socket sharing
if [[ "$cfg_wayland" == "true" ]]; then
    wayland_sock="/run/user/$(id -u)/wayland-0"
    if [[ -S "$wayland_sock" ]]; then
        podman_args+=(
            -v "$wayland_sock":"$wayland_sock"
            -e "WAYLAND_DISPLAY=wayland-0"
            -e "XDG_RUNTIME_DIR=/run/user/$(id -u)"
        )
    else
        echo "Warning: Wayland socket not found at $wayland_sock, skipping."
    fi
fi

# SSH agent sharing
if [[ "$cfg_ssh" == "true" ]]; then
    if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" ]]; then
        podman_args+=(
            -v "${SSH_AUTH_SOCK}":"${SSH_AUTH_SOCK}"
            -e "SSH_AUTH_SOCK=${SSH_AUTH_SOCK}"
        )
    else
        echo "Warning: SSH_AUTH_SOCK not set or socket missing, skipping."
    fi
fi

# .env file
if [[ -f "$dir/.env" ]]; then
    podman_args+=(--env-file "$dir/.env")
fi

# Extra volumes from config
while IFS= read -r vol; do
    [[ -n "$vol" ]] && podman_args+=(-v "$vol")
done < <(grep -E '^volumes\s*=' "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '[]"' | tr ',' '\n' | xargs -I{} echo {})

# Shared volumes from config
while IFS= read -r name; do
    if [[ -n "$name" ]]; then
        shared_path="$instances_dir/.shared/$name"
        if [[ -d "$shared_path" ]]; then
            podman_args+=(-v "$shared_path:/shared/$name")
        else
            echo "Warning: shared volume '$name' not found at $shared_path, skipping."
        fi
    fi
done < <(grep -E '^shared\s*=' "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '[]"' | tr ',' '\n' | xargs -I{} echo {})

# Extra env vars from config
while IFS= read -r var; do
    [[ -n "$var" ]] && podman_args+=(-e "$var")
done < <(grep -E '^env\s*=' "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '[]"' | tr ',' '\n' | xargs -I{} echo {})

if [[ $# -gt 0 ]]; then
    podman run "${podman_args[@]}" "$run_image" "$cfg_cmd" -c "$*"
else
    podman run "${podman_args[@]}" "$run_image" "$cfg_cmd"
fi
