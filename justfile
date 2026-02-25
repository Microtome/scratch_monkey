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

# Export a command from an instance to ~/.local/bin (bin defaults to basename of cmd)
export name cmd bin="":
    @{{scripts}}/export.sh "{{instances_dir}}" "{{base_image}}" "{{name}}" "{{cmd}}" "{{bin}}"

# Remove an exported command from ~/.local/bin
unexport bin:
    #!/usr/bin/env bash
    out="$HOME/.local/bin/{{bin}}"
    if [[ ! -f "$out" ]]; then
        echo "No file found at $out"
        exit 1
    fi
    if ! grep -q '^# scratch-dev export' "$out" 2>/dev/null; then
        echo "Warning: $out does not look like a scratch-dev export, not removing."
        exit 1
    fi
    rm "$out"
    echo "Removed $out"

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
    # Detect base image from instance Dockerfile
    instance_base=$(grep -E '^FROM\s+' "$dir/Dockerfile" 2>/dev/null | tail -1 | awk '{print $2}')
    base="${instance_base:-{{base_image}}}"
    # Ensure base image exists
    if ! podman image exists "$base"; then
        echo "Base image '$base' not found, building..."
        if [[ "$base" == *fedora* ]]; then
            podman build -t "$base" -f "{{justfile_directory()}}/Dockerfile.fedora" "{{justfile_directory()}}"
        else
            podman build -t "$base" "{{justfile_directory()}}"
        fi
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
    just root={{root}} run {{name}}

# Reset overlay container for an instance (removes persistent layer, keeps home and image)
reset name:
    #!/usr/bin/env bash
    set -euo pipefail
    container="{{name}}-overlay"
    if ! podman container exists "$container" 2>/dev/null; then
        echo "No overlay container found for '{{name}}'"
        exit 0
    fi
    read -rp "Remove overlay container for '{{name}}'? Package installs will be lost. [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    podman rm -f "$container"
    echo "Overlay container for '{{name}}' removed."

# ─── Shared volumes ───────────────────────────────────────────────────────────

# Create a shared volume
share-create name:
    #!/usr/bin/env bash
    set -euo pipefail
    shared_dir="{{instances_dir}}/.shared/{{name}}"
    if [[ -d "$shared_dir" ]]; then
        echo "Shared volume '{{name}}' already exists at $shared_dir"
        exit 1
    fi
    mkdir -p "$shared_dir"
    echo "Created shared volume '{{name}}' at $shared_dir"

# Delete a shared volume
share-delete name:
    #!/usr/bin/env bash
    set -euo pipefail
    shared_dir="{{instances_dir}}/.shared/{{name}}"
    if [[ ! -d "$shared_dir" ]]; then
        echo "Error: shared volume '{{name}}' not found at $shared_dir"
        exit 1
    fi
    read -rp "Delete shared volume '{{name}}' and all its data? [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    # Remove from all instance configs
    for inst_dir in "{{instances_dir}}"/*/; do
        [[ "$(basename "$inst_dir")" == ".shared" ]] && continue
        conf="$inst_dir/scratch.toml"
        [[ -f "$conf" ]] || continue
        if grep -qE '^shared\s*=' "$conf"; then
            current=$(grep -E '^shared\s*=' "$conf" | sed 's/^[^=]*=\s*//' | tr -d '[]" ')
            if echo "$current" | tr ',' '\n' | grep -qx '{{name}}'; then
                inst=$(basename "$inst_dir")
                new_list=$(echo "$current" | tr ',' '\n' | grep -vx '{{name}}' | paste -sd,)
                if [[ -z "$new_list" ]]; then
                    sed -i '/^shared\s*=/d' "$conf"
                else
                    formatted=$(echo "$new_list" | sed 's/,/", "/g')
                    sed -i 's/^shared\s*=.*/shared = ["'"$formatted"'"]/' "$conf"
                fi
                echo "Removed '{{name}}' from instance '$inst'"
            fi
        fi
    done
    rm -rf "$shared_dir"
    echo "Deleted shared volume '{{name}}'"

# Add a shared volume to an instance's config
share-add name instance:
    #!/usr/bin/env bash
    set -euo pipefail
    shared_dir="{{instances_dir}}/.shared/{{name}}"
    conf="{{instances_dir}}/{{instance}}/scratch.toml"
    if [[ ! -d "$shared_dir" ]]; then
        echo "Error: shared volume '{{name}}' does not exist. Run: just share-create {{name}}"
        exit 1
    fi
    if [[ ! -f "$conf" ]]; then
        echo "Error: instance '{{instance}}' not found"
        exit 1
    fi
    # Check if shared key exists (uncommented)
    if grep -qE '^shared\s*=' "$conf"; then
        current=$(grep -E '^shared\s*=' "$conf" | sed 's/^[^=]*=\s*//' | tr -d '[]" ')
        # Check if already present
        if echo "$current" | tr ',' '\n' | grep -qx '{{name}}'; then
            echo "Shared volume '{{name}}' already in {{instance}}'s config"
            exit 0
        fi
        # Append to existing list
        if [[ -z "$current" ]]; then
            sed -i 's/^shared\s*=.*/shared = ["{{name}}"]/' "$conf"
        else
            new_list=$(echo "$current" | sed 's/,/", "/g')
            sed -i 's/^shared\s*=.*/shared = ["'"$new_list"'", "{{name}}"]/' "$conf"
        fi
    else
        echo 'shared = ["{{name}}"]' >> "$conf"
    fi
    echo "Added shared volume '{{name}}' to instance '{{instance}}'"

# Remove a shared volume from an instance's config
share-remove name instance:
    #!/usr/bin/env bash
    set -euo pipefail
    conf="{{instances_dir}}/{{instance}}/scratch.toml"
    if [[ ! -f "$conf" ]]; then
        echo "Error: instance '{{instance}}' not found"
        exit 1
    fi
    if ! grep -qE '^shared\s*=' "$conf"; then
        echo "Instance '{{instance}}' has no shared volumes configured"
        exit 0
    fi
    current=$(grep -E '^shared\s*=' "$conf" | sed 's/^[^=]*=\s*//' | tr -d '[]" ')
    if ! echo "$current" | tr ',' '\n' | grep -qx '{{name}}'; then
        echo "Shared volume '{{name}}' not in {{instance}}'s config"
        exit 0
    fi
    # Build new list without the removed name
    new_list=$(echo "$current" | tr ',' '\n' | grep -vx '{{name}}' | paste -sd,)
    if [[ -z "$new_list" ]]; then
        sed -i '/^shared\s*=/d' "$conf"
    else
        formatted=$(echo "$new_list" | sed 's/,/", "/g')
        sed -i 's/^shared\s*=.*/shared = ["'"$formatted"'"]/' "$conf"
    fi
    echo "Removed shared volume '{{name}}' from instance '{{instance}}'"

# List all shared volumes and which instances use them
share-list:
    #!/usr/bin/env bash
    set -euo pipefail
    shared_base="{{instances_dir}}/.shared"
    if [[ ! -d "$shared_base" ]] || [[ -z "$(ls -A "$shared_base" 2>/dev/null)" ]]; then
        echo "No shared volumes found."
        exit 0
    fi
    printf "%-20s %s\n" "VOLUME" "USED BY"
    for vol_dir in "$shared_base"/*/; do
        vol=$(basename "$vol_dir")
        users=""
        for inst_dir in "{{instances_dir}}"/*/; do
            [[ "$(basename "$inst_dir")" == ".shared" ]] && continue
            conf="$inst_dir/scratch.toml"
            [[ -f "$conf" ]] || continue
            if grep -qE '^shared\s*=' "$conf"; then
                list=$(grep -E '^shared\s*=' "$conf" | sed 's/^[^=]*=\s*//' | tr -d '[]" ')
                if echo "$list" | tr ',' '\n' | grep -qx "$vol"; then
                    inst=$(basename "$inst_dir")
                    if [[ -n "$users" ]]; then
                        users="$users, $inst"
                    else
                        users="$inst"
                    fi
                fi
            fi
        done
        printf "%-20s %s\n" "$vol" "${users:-(none)}"
    done

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
