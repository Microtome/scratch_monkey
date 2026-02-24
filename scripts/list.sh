#!/usr/bin/env bash

# Usage: list.sh <instances_dir>
dir="$1"

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
