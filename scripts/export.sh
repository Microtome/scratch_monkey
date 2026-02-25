#!/usr/bin/env bash
set -euo pipefail

# Usage: export.sh <instances_dir> <base_image> <name> <cmd> [bin_name]
instances_dir="$1"
base_image="$2"
name="$3"
cmd="$4"
bin_name="${5:-$(basename "$cmd")}"

dir="$instances_dir/$name"
conf="$dir/scratch.toml"

if [[ ! -d "$dir" ]]; then
    echo "Error: instance '$name' not found at $dir"
    exit 1
fi

# Read home config
cfg_home=$(grep -E '^home\s*=' "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '"' | tr -d "'" | xargs || true)
if [[ -n "$cfg_home" ]]; then
    home_dir="$cfg_home"
else
    home_dir="$dir/home"
fi

container_home="/home/$USER"
bin_dir="$HOME/.local/bin"
out="$bin_dir/$bin_name"

mkdir -p "$bin_dir"

# Determine image at export time as the default; script re-checks at runtime
if podman image exists "$name" 2>/dev/null; then
    default_image="$name"
else
    default_image="$base_image"
fi

cat > "$out" <<SCRIPT
#!/bin/sh
# scratch-dev export
# instance: $name
# command: $cmd
if [ "\${SCRATCH_INSTANCE:-}" = "$name" ]; then
    exec "$cmd" "\$@"
fi
if podman container inspect "${name}-overlay" --format '{{.State.Status}}' 2>/dev/null | grep -q '^running\$'; then
    if [ -t 1 ]; then
        exec podman exec -it "${name}-overlay" "$cmd" "\$@"
    else
        exec podman exec -i "${name}-overlay" "$cmd" "\$@"
    fi
fi
if podman image exists "$name" 2>/dev/null; then
    _image="$name"
else
    _image="$base_image"
fi
if [ -t 1 ]; then _tty="-t"; else _tty=""; fi
exec podman run --rm -i \$_tty \\
    --security-opt label=disable \\
    --network=host \\
    --hostname "${name}.$(hostname -s)" \\
    -e HOME="$container_home" \\
    -e USER="$USER" \\
    -e SCRATCH_INSTANCE="$name" \\
    -v "${home_dir}:${container_home}" \\
    "\$_image" "$cmd" "\$@"
SCRIPT

chmod +x "$out"
echo "Exported '$cmd' from '$name' → $out"
