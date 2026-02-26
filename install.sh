#!/usr/bin/env bash
# scratch-monkey install script
set -euo pipefail

TOOL_NAME="scratch-monkey"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/scratch-monkey"

# ─── Check for uv ─────────────────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    echo "uv is not installed."
    read -rp "Install uv now? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Re-source to pick up uv in PATH
        export PATH="$HOME/.cargo/bin:$PATH"
        if ! command -v uv &>/dev/null; then
            echo "uv installed but not in PATH. Please add ~/.cargo/bin to your PATH and re-run."
            exit 1
        fi
    else
        echo "uv is required. Install it from https://github.com/astral-sh/uv"
        exit 1
    fi
fi

# ─── Install ──────────────────────────────────────────────────────────────────

# Parse options
WITH_GUI=false
for arg in "$@"; do
    case "$arg" in
        --gui) WITH_GUI=true ;;
    esac
done

INSTALL_SPEC="."
if $WITH_GUI; then
    INSTALL_SPEC=".[gui]"
fi

echo "Installing $TOOL_NAME..."
uv tool install --editable "$INSTALL_SPEC" --force

# ─── PATH check ───────────────────────────────────────────────────────────────

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    echo ""
    echo "Warning: $BIN_DIR is not in your PATH."
    echo "Add the following to your shell config (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# ─── Config directory ─────────────────────────────────────────────────────────

mkdir -p "$CONFIG_DIR"

# ─── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "✓ scratch-monkey installed successfully!"
echo ""
echo "Quick start:"
echo "  scratch-monkey create myproject"
echo "  scratch-monkey enter myproject"
echo ""
echo "For help:"
echo "  scratch-monkey --help"
