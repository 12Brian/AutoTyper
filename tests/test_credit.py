"""Tests for the developer credit shown in the interface.

The credit is a user-visible attribution, so these guard against it silently
disappearing in a refactor.

Important testing notes:

* ``MainWindow`` registers **global hotkeys**, which start pynput hook threads.
  A leaked hook thread aborted the interpreter later in the run ("access memory
  violation"), so the fixture stops them explicitly and the widget tests reuse
  one window.
* ``MainWindow.closeEvent`` **persists settings**, so the data directory is
  redirected to a temp folder and running the suite can never overwrite the
  developer's real ``settings.json``.
"""

from __future__ import annotations

import os

import pytest
from autotyper import __author__, __version__

# Must be set before any Qt widget is constructed by these tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ------------------------------------------------------------------ pure checks
def test_author_is_defined() -> None:
    """The package exposes a non-empty author string for every surface to use."""
    assert isinstance(__author__, str)
    assert __author__.strip(), "author must not be blank"
    assert __author__ == __author__.strip(), "author must not carry stray whitespace"


def test_author_is_exported() -> None:
    """``__all__`` advertises the author so wildcard imports keep working."""
    import autotyper

    assert "__author__" in autotyper.__all__


def test_theme_defines_the_credit_role() -> None:
    """The credit pill needs a style role, otherwise it renders as plain text."""
    from autotyper.ui import theme

    with open(theme.__file__, encoding="utf-8") as handle:
        qss = handle.read()
    assert 'QLabel[role="credit"]' in qss, "credit role missing from the stylesheet"


# ------------------------------------------------------------------ Qt fixtures
@pytest.fixture(scope="module")
def qt_app():
    """Provide one QApplication for this module (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def window(qt_app, tmp_path_factory):
    """Build one MainWindow and tear its native hooks down afterwards.

    ``hotkeys.stop()`` is called explicitly because a leaked pynput hook thread
    crashes the interpreter later in the suite; ``closeEvent`` should already do
    this, and the explicit call means a future change cannot regress it.
    """
    from autotyper.config.models import AppSettings
    from autotyper.config.paths import settings_file
    from autotyper.core import platform as platform_info
    from autotyper.ui.main_window import MainWindow

    os.environ["AUTOTYPER_DATA_DIR"] = str(tmp_path_factory.mktemp("autotyper_data"))
    assert "autotyper_data" in str(settings_file()), "data dir override did not apply"

    win = MainWindow(AppSettings(), platform_info.check_keyboard_access())
    win.show()
    qt_app.processEvents()
    yield win
    win.close()
    win.hotkeys.stop()
    win.deleteLater()
    qt_app.processEvents()


# --------------------------------------------------------------- widget checks
def test_header_shows_the_developer_credit(window) -> None:
    """The main window header displays "Developer: <author>" next to the title."""
    label = window.credit_label
    assert label.text() == f"Developer: {__author__}"
    assert label.property("role") == "credit"
    # Screen readers cannot infer a QSS role, so it is spelled out.
    assert label.accessibleName() == f"Developer: {__author__}"
    assert __version__ in label.toolTip()
    assert __author__ in label.toolTip()


def test_credit_sits_beside_the_title(window, qt_app) -> None:
    """The credit is level with, and to the right of, the "AutoTyper" title."""
    from PySide6.QtWidgets import QLabel

    qt_app.processEvents()
    titles = [
        child for child in window.findChildren(QLabel) if child.property("role") == "title"
    ]
    assert titles, "title label not found"
    title = titles[0].geometry()
    credit = window.credit_label.geometry()

    assert credit.left() > title.right(), "credit should sit to the right of the title"
    assert abs(credit.center().y() - title.center().y()) < 12, "credit should be level"


def test_about_tab_shows_the_developer_credit(qt_app) -> None:
    """Preferences → About repeats the attribution."""
    from autotyper.config.models import AppSettings
    from autotyper.core import platform as platform_info
    from autotyper.ui.settings_dialog import SettingsDialog
    from PySide6.QtWidgets import QLabel

    dialog = SettingsDialog(AppSettings(), platform_info.check_keyboard_access())
    try:
        texts = [
            child.text()
            for child in dialog.findChildren(QLabel)
            if child.property("role") == "credit"
        ]
        assert f"Developer: {__author__}" in texts
    finally:
        dialog.close()
