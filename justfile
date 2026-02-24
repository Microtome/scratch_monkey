# scratch-dev justfile

# Configurable
base_image := "scratch_dev"
instances_dir := env("HOME") / "scratch-dev"

# CLI overrides for run (e.g., just wayland=true run myproject)
wayland := ""
ssh := ""
cmd := ""
_root := ""

# ─── Config parsing ──────────────────────────────────────────────────────────

[private]
@get-config file key default:
    #!/usr/bin/env bash
    val=$(grep -E "^{{key}}\s*=" "{{file}}" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '"' | tr -d "'" | xargs)
    echo "${val:-{{default}}}"

# ─── Instance management ─────────────────────────────────────────────────────

# Create a new scratch-dev instance
create name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{instances_dir}}/{{name}}"
    if [[ -d "$dir" ]]; then
        echo "Error: instance '{{name}}' already exists at $dir"
        exit 1
    fi
    mkdir -p "$dir/home"
    cp "{{justfile_directory()}}/scratch.toml.default" "$dir/scratch.toml"
    cat > "$dir/Dockerfile" <<'DOCKERFILE'
    FROM scratch_dev
    # Add your customizations here.
    # COPY and ADD work. RUN does not (no shell in image).
    # Use multi-stage builds to pull binaries from other images.
    DOCKERFILE
    # Trim leading whitespace from heredoc
    sed -i 's/^    //' "$dir/Dockerfile"
    touch "$dir/.env"
    echo "Created instance '{{name}}' at $dir"
    echo ""
    echo "Next steps:"
    echo "  Edit config:      \$EDITOR $dir/scratch.toml"
    echo "  Edit Dockerfile:  \$EDITOR $dir/Dockerfile"
    echo "  Add secrets:      \$EDITOR $dir/.env"
    echo "  Run:              just run {{name}}"

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

# List all instances
list:
    #!/usr/bin/env bash
    dir="{{instances_dir}}"
    if [[ ! -d "$dir" ]] || [[ -z "$(ls -A "$dir" 2>/dev/null)" ]]; then
        echo "No instances found. Create one with: just create <name>"
        exit 0
    fi
    printf "%-20s %-15s %-40s %s\n" "INSTANCE" "IMAGE BUILT" "DIRECTORY" "CONFIG"
    for instance_dir in "$dir"/*/; do
        [[ -d "$instance_dir" ]] || continue
        name=$(basename "$instance_dir")
        if podman image exists "$name" 2>/dev/null; then
            built="yes"
        else
            built="no"
        fi
        config="(defaults)"
        conf_file="$instance_dir/scratch.toml"
        if [[ -f "$conf_file" ]]; then
            active=$(grep -E '^[a-z]' "$conf_file" 2>/dev/null | sed 's/\s*=\s*/=/' | tr '\n' ', ' | sed 's/,$//')
            [[ -n "$active" ]] && config="$active"
        fi
        printf "%-20s %-15s %-40s %s\n" "$name" "$built" "${instance_dir%/}" "$config"
    done

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
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{instances_dir}}/{{name}}"
    conf="$dir/scratch.toml"
    if [[ ! -d "$dir" ]]; then
        echo "Error: instance '{{name}}' not found at $dir"
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

    cfg_cmd=$(get "cmd" "/bin/bash" "{{cmd}}")
    cfg_wayland=$(get "wayland" "false" "{{wayland}}")
    cfg_ssh=$(get "ssh" "false" "{{ssh}}")
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
    if podman image exists "{{name}}" 2>/dev/null; then
        run_image="{{name}}"
    else
        run_image="{{base_image}}"
        # Ensure base image exists
        if ! podman image exists "$run_image"; then
            echo "Base image '$run_image' not found, building..."
            podman build -t "$run_image" "{{justfile_directory()}}"
        fi
    fi

    # Base podman arguments
    podman_args=(
        --rm -it
        --security-opt label=disable
        --network=host
        -e "HOME=$home_dir"
        -v /usr:/usr:ro
        -v /etc:/etc:ro
        -v /var/usrlocal:/var/usrlocal:ro
        -v /var/opt:/var/opt:ro
        -v /var/usrlocal:/usr/local:ro
        -v "$home_dir":"$home_dir"
    )

    # Run as current user unless root mode requested
    if [[ "{{_root}}" != "true" ]]; then
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

    # Extra env vars from config
    while IFS= read -r var; do
        [[ -n "$var" ]] && podman_args+=(-e "$var")
    done < <(grep -E '^env\s*=' "$conf" 2>/dev/null | sed 's/^[^=]*=\s*//' | tr -d '[]"' | tr ',' '\n' | xargs -I{} echo {})

    args="{{args}}"
    if [[ -n "$args" ]]; then
        podman run "${podman_args[@]}" "$run_image" "$cfg_cmd" -c "$args"
    else
        podman run "${podman_args[@]}" "$run_image" "$cfg_cmd"
    fi

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
