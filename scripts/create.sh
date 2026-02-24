#!/usr/bin/env bash
set -euo pipefail

# Usage: create.sh <instances_dir> <name> <project_dir>
instances_dir="$1"
name="$2"
project_dir="$3"

dir="$instances_dir/$name"
if [[ -d "$dir" ]]; then
    echo "Error: instance '$name' already exists at $dir"
    exit 1
fi
mkdir -p "$dir/home"
cp "$project_dir/scratch.toml.default" "$dir/scratch.toml"
cat > "$dir/Dockerfile" <<'DOCKERFILE'
FROM scratch_dev
# Add your customizations here.
# COPY and ADD work. RUN does not (no shell in image).
# Use multi-stage builds to pull binaries from other images.
DOCKERFILE
touch "$dir/.env"
echo "Created instance '$name' at $dir"
echo ""
echo "Next steps:"
echo "  Edit config:      \$EDITOR $dir/scratch.toml"
echo "  Edit Dockerfile:  \$EDITOR $dir/Dockerfile"
echo "  Add secrets:      \$EDITOR $dir/.env"
echo "  Run:              just run $name"
