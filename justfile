# scratch-monkey developer justfile
# For end-user usage, see: scratch-monkey --help

# Run tests
test:
    python3 -m pytest

# Run tests with coverage
test-cov:
    python3 -m pytest --cov=scratch_monkey --cov-report=term-missing

# Run integration tests (requires real podman)
test-integration:
    python3 -m pytest -m integration

# Lint source and tests
lint:
    python3 -m ruff check src tests

# Format source and tests
fmt:
    python3 -m ruff format src tests

# Lint + format check (CI mode)
check:
    python3 -m ruff check src tests
    python3 -m ruff format --check src tests

# Install the tool in development mode
install:
    pip install -e ".[dev]"

# Install with GUI dependencies
install-gui:
    pip install -e ".[gui,dev]"

# Uninstall the tool
uninstall:
    pip uninstall scratch-monkey

# Build distribution packages
build:
    python3 -m build

# Show CLI help
show:
    scratch-monkey --help
