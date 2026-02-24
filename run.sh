#!/bin/bash

IMAGE="scratch_dev-app"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "Usage: $0 --home <dir> [-- <command>...]"
  echo "  --home <dir>   Home directory to mount (required)"
  exit 1
}

# Parse args
USER_HOME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) USER_HOME="$2"; shift 2 ;;
    --)     shift; break ;;
    *)      break ;;
  esac
done

if [[ -z "$USER_HOME" ]]; then
  usage
fi

# Check if home directory exists
if [[ ! -d "$USER_HOME" ]]; then
  read -rp "'$USER_HOME' does not exist. Create it? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    mkdir -p "$USER_HOME" || exit 1
  else
    exit 1
  fi
fi

# Build image if it doesn't exist
if ! podman image exists "$IMAGE"; then
  echo "Image '$IMAGE' not found, building..."
  podman build -t "$IMAGE" "$SCRIPT_DIR" || exit 1
fi

podman run --rm -it \
  --userns=keep-id \
  --security-opt label=disable \
  --network=host \
  -e "HOME=$USER_HOME" \
  -v /usr:/usr:ro \
  -v /etc:/etc:ro \
  -v /var/usrlocal:/var/usrlocal:ro \
  -v /var/opt:/var/opt:ro \
  -v /var/usrlocal:/usr/local:ro \
  -v "$USER_HOME":"$USER_HOME" \
  "$IMAGE" /bin/bash "$@"
