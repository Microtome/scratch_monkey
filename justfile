# scratch-dev justfile

# Configurable
base_image := "scratch_dev"
fedora_image := "scratch_dev_fedora"
instances_dir := env("HOME") / "scratch-dev"

# Flags
fedora := ""
skel := ""
root := ""
wayland := ""
ssh := ""
cmd := ""

scripts := justfile_directory() / "scripts"

# Resolve base image based on fedora flag
_base := if fedora == "true" { fedora_image } else { base_image }

# ─── Instance management ─────────────────────────────────────────────────────

# Create a new scratch-dev instance (fedora=true for fedora base, skel=true to copy shell configs)
create name:
    #!/usr/bin/env bash
    "{{scripts}}/create.sh" "{{instances_dir}}" "{{name}}" "{{justfile_directory()}}" "{{_base}}"
    if [[ "{{skel}}" == "true" ]]; then
        "{{scripts}}/skel.sh" "{{instances_dir}}" "{{name}}"
    fi

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

# Edit an instance file: config, dockerfile, or env
edit name file="config":
    #!/usr/bin/env bash
    dir="{{instances_dir}}/{{name}}"
    case "{{file}}" in
        config)     ${EDITOR:-vi} "$dir/scratch.toml" ;;
        dockerfile) ${EDITOR:-vi} "$dir/Dockerfile" ;;
        env)        ${EDITOR:-vi} "$dir/.env" ;;
        *)          echo "Unknown file '{{file}}'. Use: config, dockerfile, or env"; exit 1 ;;
    esac

# ─── Info ─────────────────────────────────────────────────────────────────────

# List all instances
list:
    @{{scripts}}/list.sh "{{instances_dir}}"

# ─── Build ────────────────────────────────────────────────────────────────────

# Build a base image (fedora=true for fedora base)
build:
    #!/usr/bin/env bash
    set -euo pipefail
    image="{{_base}}"
    if podman image exists "$image"; then
        read -rp "Image '$image' already exists. Rebuild? [y/N] " answer
        [[ "$answer" =~ ^[Yy]$ ]] || exit 0
    fi
    if [[ "{{fedora}}" == "true" ]]; then
        podman build -t "$image" -f "{{justfile_directory()}}/Dockerfile.fedora" "{{justfile_directory()}}"
    else
        podman build -t "$image" "{{justfile_directory()}}"
    fi

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
    @{{scripts}}/run.sh "{{instances_dir}}" "{{base_image}}" "{{justfile_directory()}}" "{{name}}" "{{root}}" "{{wayland}}" "{{ssh}}" "{{cmd}}" {{args}}

# Convenience alias for interactive shell
shell name *args="":
    just run {{name}} {{args}}

# Drop into an interactive shell (root=true for root shell)
enter name:
    just _root={{root}} run {{name}}

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
    echo "Fedora image: {{fedora_image}}"
    podman image exists "{{fedora_image}}" && echo "  Built: yes" || echo "  Built: no"
    echo "Instances dir: {{instances_dir}}"
    echo ""
    just list
