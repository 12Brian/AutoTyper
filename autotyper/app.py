"""Application bootstrap: logging, settings, capability probe and the main window."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__
from .config.jsonstore import JsonStore
from .config.models import AppSettings
from .config.paths import ensure_app_data_dir, log_file, settings_file
from .core import platform as platform_info

LOGGER = logging.getLogger(__name__)

#: Set by PyInstaller so bundled resources can be located.
FROZEN = getattr(sys, "frozen", False)


def resource_path(*parts: str) -> Path:
    """Return the path of a bundled resource.

    Args:
        *parts: Path components relative to the package root.

    Returns:
        An absolute path that works both from source and inside a PyInstaller
        one-file bundle (where data files live in ``sys._MEIPASS``).
    """
    if FROZEN:
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base.joinpath("autotyper", *parts)
    return Path(__file__).resolve().parent.joinpath(*parts)


def configure_logging(level: int = logging.INFO) -> None:
    """Set up console + rotating-file logging.

    The file handler is best-effort: a read-only data directory must never stop
    the application from starting.

    Args:
        level: Root log level.
    """
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler(stream=sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        ensure_app_data_dir()
        file_handler = logging.handlers.RotatingFileHandler(
            log_file(), maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - permissions dependent
        LOGGER.warning("File logging disabled (%s); using the console only", exc)


def load_settings() -> AppSettings:
    """Load ``settings.json``, falling back to defaults when unusable."""
    try:
        store = JsonStore(settings_file(), defaults=AppSettings().to_dict())
        return AppSettings.from_dict(store.load())
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Could not load settings, using defaults: %s", exc)
        return AppSettings()


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create (or return) the ``QApplication`` with app-wide metadata.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        The application instance.
    """
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("AutoTyper")
    app.setApplicationDisplayName("AutoTyper")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("AutoTyper")
    app.setOrganizationDomain("autotyper.local")
    app.setDesktopFileName("autotyper")
    app.setQuitOnLastWindowClosed(True)

    # Use the OS locale for number formatting but keep English UI strings.
    QLocale.setDefault(QLocale(QLocale.Language.English))

    icon_path = resource_path("assets", "autotyper.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    return app


def main(argv: list[str] | None = None) -> int:
    """Application entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        Process exit code.
    """
    configure_logging()
    LOGGER.info("Starting AutoTyper %s on Python %s", __version__, sys.version.split()[0])

    if not platform_info.is_gui_available():
        LOGGER.error("No graphical session detected (DISPLAY/WAYLAND_DISPLAY unset)")
        print(
            "AutoTyper needs a graphical session. Run it from your desktop, or set "
            "DISPLAY/WAYLAND_DISPLAY when forwarding over SSH.",
            file=sys.stderr,
        )
        return 2

    app = create_application(argv)

    # The capability probe constructs a pynput controller, which is fast but
    # must never be done before QApplication exists on macOS (it needs the
    # window server connection).
    report = platform_info.check_keyboard_access()
    LOGGER.info("Platform probe: %s (%s)", report.summary, report.severity)

    settings = load_settings()

    from .ui.main_window import MainWindow

    window = MainWindow(settings, report)

    if report.needs_attention:
        LOGGER.warning("Keyboard access needs attention: %s", report.summary)

    window.show()
    exit_code = app.exec()
    LOGGER.info("AutoTyper exited with code %s", exit_code)
    return int(exit_code)


if __name__ == "__main__":  # pragma: no cover - manual launch
    raise SystemExit(main())
