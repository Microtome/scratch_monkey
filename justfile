# scratch-dev justfile

# Configurable
base_image := "scratch_dev"
instances_dir := env("HOME") / "scratch-dev"

# CLI overrides for run (e.g., just wayland=true run myproject)
wayland := ""
ssh := ""
cmd := ""
_root := ""

scripts := justfile_directory() / "scripts"

# ─── Instance management ─────────────────────────────────────────────────────

# Create a new scratch-dev instance
create name:
    @{{scripts}}/create.sh "{{instances_dir}}" "{{name}}" "{{justfile_directory()}}"

# Clone an existing instance (copies Dockerfile + config, fresh home/)
clone source dest:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{instances_dir}}/{{source}}"
    dst="{{instances_dir}}/{{dest}}"
    if [[ ! -d "$src" ]]; then
        echo "Error: source instance '{{source}}' not found at $src"
        exit 1
    fi
    if [[ -d "$dst" ]]; then
        echo "Error: destination instance '{{dest}}' already exists at $dst"
        exit 1
    fi
    mkdir -p "$dst/home"
    cp "$src/Dockerfile" "$dst/Dockerfile"
    cp "$src/scratch.toml" "$dst/scratch.toml"
    [[ -f "$src/.env" ]] && cp "$src/.env" "$dst/.env" || touch "$dst/.env"
    echo "Cloned '{{source}}' → '{{dest}}' (fresh home directory)"

# Delete an instance (removes directory + image)
delete name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{instances_dir}}/{{name}}"
    if [[ ! -d "$dir" ]]; then
        echo "Error: instance '{{name}}' not found at $dir"
        exit 1
    fi
    read -rp "Delete instance '{{name}}' and all its data? [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    podman rmi "{{name}}" 2>/dev/null && echo "Removed image '{{name}}'" || true
    rm -rf "$dir"
    echo "Deleted instance '{{name}}'"

# Copy skeleton bash config files from /etc/skel into instance home
skel name:
    @{{scripts}}/skel.sh "{{instances_dir}}" "{{name}}"

# List all instances
list:
    @{{scripts}}/list.sh "{{instances_dir}}"

# ─── Build ────────────────────────────────────────────────────────────────────

# Build the base scratch_dev image
build:
    #!/usr/bin/env bash
    set -euo pipefail
    if podman image exists "{{base_image}}"; then
        read -rp "Base image '{{base_image}}' already exists. Rebuild? [y/N] " answer
        [[ "$answer" =~ ^[Yy]$ ]] || exit 0
    fi
    podman build -t "{{base_image}}" "{{justfile_directory()}}"

# Build an instance's Dockerfile (tagged as the instance name)
build-instance name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{instances_dir}}/{{name}}"
    if [[ ! -d "$dir" ]]; then
        echo "Error: instance '{{name}}' not found at $dir"
        exit 1
    fi
    # Ensure base image exists
    if ! podman image exists "{{base_image}}"; then
        echo "Base image '{{base_image}}' not found, building..."
        podman build -t "{{base_image}}" "{{justfile_directory()}}"
    fi
    podman build -t "{{name}}" -f "$dir/Dockerfile" "$dir"

# ─── Run ──────────────────────────────────────────────────────────────────────

# Run a scratch-dev instance
run name *args="":
    @{{scripts}}/run.sh "{{instances_dir}}" "{{base_image}}" "{{justfile_directory()}}" "{{name}}" "{{_root}}" "{{wayland}}" "{{ssh}}" "{{cmd}}" {{args}}

# Convenience alias for interactive shell
shell name *args="":
    just run {{name}} {{args}}

# Drop into an interactive bash shell in the instance
enter name:
    just run {{name}}

# Drop into an interactive root shell in the instance
enter-root name:
    just _root=true run {{name}}

# ─── Maintenance ──────────────────────────────────────────────────────────────

# Remove the base image
clean:
    #!/usr/bin/env bash
    podman rmi "{{base_image}}" 2>/dev/null && echo "Removed {{base_image}}" || echo "{{base_image}} not found"

# Remove an instance's image
clean-instance name:
    #!/usr/bin/env bash
    podman rmi "{{name}}" 2>/dev/null && echo "Removed image '{{name}}'" || echo "Image '{{name}}' not found"

# Show base image info and all instances
status:
    #!/usr/bin/env bash
    echo "=== scratch-dev status ==="
    echo "Base image: {{base_image}}"
    podman image exists "{{base_image}}" && echo "  Built: yes" || echo "  Built: no"
    echo "Instances dir: {{instances_dir}}"
    echo ""
    just list
