# scratch-monkey developer justfile
# For end-user usage, see: scratch-monkey --help

# Run tests
test:
    uv run pytest

# Run tests with coverage
test-cov:
    uv run pytest --cov=scratch_monkey --cov-report=term-missing

# Run integration tests (requires real podman)
test-integration:
    uv run pytest -m integration

# Lint source and tests
lint:
    uv run ruff check src tests

# Format source and tests
fmt:
    uv run ruff format src tests

# Lint + format check (CI mode)
check:
    uv run ruff check src tests
    uv run ruff format --check src tests

# Install the tool in development mode
install:
    uv tool install --editable .

# Install with GUI dependencies
install-gui:
    uv tool install --editable ".[gui]"

# Uninstall the tool
uninstall:
    uv tool uninstall scratch-monkey

# Build distribution packages
build:
    uv build

# Show CLI help
show:
    scratch-monkey --help
