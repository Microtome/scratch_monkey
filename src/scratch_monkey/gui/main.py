"""GUI entry point for scratch-monkey."""

from __future__ import annotations

import sys
from pathlib import Path


def main(instances_dir: Path | None = None) -> None:
    """Launch the scratch-monkey GUI application."""
    try:
        import enaml
    except ImportError:
        print(
            "Error: GUI dependencies not installed.\n"
            "Install with: pip install 'scratch-monkey[gui]'",
            file=sys.stderr,
        )
        sys.exit(1)


    from ..container import PodmanRunner
    from .models import AppModel

    if instances_dir is None:
        instances_dir = Path.home() / "scratch-monkey"
    runner = PodmanRunner()
    app_model = AppModel(instances_dir, runner)

    with enaml.imports():
        from .views.main_window import ScratchMonkeyWindow

    from enaml.qt.qt_application import QtApplication

    app = QtApplication()
    view = ScratchMonkeyWindow(app_model=app_model)
    view.show()
    app.start()
