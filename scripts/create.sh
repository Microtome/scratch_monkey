#!/usr/bin/env bash
set -euo pipefail

# Usage: create.sh <instances_dir> <name> <project_dir> [base_image]
instances_dir="$1"
name="$2"
project_dir="$3"
base_image="${4:-scratch_dev}"

dir="$instances_dir/$name"
if [[ -d "$dir" ]]; then
    echo "Error: instance '$name' already exists at $dir"
    exit 1
fi
mkdir -p "$dir/home"
cp "$project_dir/scratch.toml.default" "$dir/scratch.toml"

if [[ "$base_image" == *fedora* ]]; then
    cat > "$dir/Dockerfile" <<DOCKERFILE
FROM $base_image
# Add your customizations here.
# Full Fedora base — RUN, COPY, and ADD all work.
DOCKERFILE
else
    cat > "$dir/Dockerfile" <<DOCKERFILE
FROM $base_image
# Add your customizations here.
# COPY and ADD work. RUN does not (no shell in image).
# Use multi-stage builds to pull binaries from other images.
DOCKERFILE
fi

touch "$dir/.env"
echo "Created instance '$name' at $dir (base: $base_image)"
echo ""
echo "Next steps:"
echo "  Edit config:      just edit $name"
echo "  Edit Dockerfile:  just edit $name dockerfile"
echo "  Add secrets:      just edit $name env"
echo "  Run:              just enter $name"
