#!/usr/bin/env bash
set -euo pipefail

# Usage: skel.sh <instances_dir> <name>
instances_dir="$1"
name="$2"

dir="$instances_dir/$name"
if [[ ! -d "$dir" ]]; then
    echo "Error: instance '$name' not found at $dir"
    exit 1
fi
home_dir="$dir/home"
copied=0
for f in /etc/skel/.*; do
    base=$(basename "$f")
    [[ "$base" == "." || "$base" == ".." ]] && continue
    if [[ -e "$home_dir/$base" ]]; then
        echo "  Skipping $base (already exists)"
    else
        cp -a "$f" "$home_dir/$base"
        echo "  Copied $base"
        copied=$((copied + 1))
    fi
done
if [[ $copied -eq 0 ]]; then
    echo "No new files copied (all already exist)."
else
    echo "Copied $copied file(s) from /etc/skel to $home_dir"
fi
