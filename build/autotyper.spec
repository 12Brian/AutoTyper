# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for AutoTyper.

Produces a one-folder app bundle on every platform:

* Windows -> ``dist/AutoTyper/AutoTyper.exe``
* macOS   -> ``dist/AutoTyper.app``
* Linux   -> ``dist/AutoTyper/AutoTyper``

One-folder is deliberate: PySide6 is large, so a one-file bundle would unpack
tens of megabytes on every launch (slow, and it breaks macOS code signing).
``build/build_*.sh``/``.ps1`` wrap this spec with the right options per platform.

Usage::

    pyinstaller build/autotyper.spec --noconfirm
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ``SPECPATH`` is injected by PyInstaller and points at build/.
PROJECT_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - provided by PyInstaller
ASSETS = PROJECT_ROOT / "assets"
PACKAGE = PROJECT_ROOT / "autotyper"


def asset_data() -> list[tuple[str, str]]:
    """Return ``(source, destination)`` pairs for bundled data files.

    The destination mirrors the package layout so ``autotyper.app.resource_path``
    finds the icons both from source and from a frozen bundle.
    """
    wanted = ["autotyper.png", "autotyper.ico", "autotyper.icns"]
    pairs: list[tuple[str, str]] = []
    for name in wanted:
        source = ASSETS / name
        if source.exists():
            pairs.append((str(source), str(Path("autotyper") / "assets")))
    return pairs


def icon_for_platform() -> str | None:
    """Return the platform's icon path, or ``None`` when unavailable."""
    if sys.platform == "win32":
        candidate = ASSETS / "autotyper.ico"
    elif sys.platform == "darwin":
        candidate = ASSETS / "autotyper.icns"
    else:
        candidate = ASSETS / "autotyper.png"
    return str(candidate) if candidate.exists() else None


def hidden_imports() -> list[str]:
    """Modules that PyInstaller's static analysis cannot always see.

    ``pynput`` selects its backend at import time via ``importlib``, and Qt's
    platform/style plugins are loaded dynamically, so both need help.
    """
    imports = [
        "pynput",
        "pynput.keyboard",
        "pynput.keyboard._base",
        "pynput._util",
        "pynput._util.xorg",
    ]
    if sys.platform == "win32":
        imports += ["pynput.keyboard._win32", "pynput.mouse._win32"]
    elif sys.platform == "darwin":
        imports += ["pynput.keyboard._darwin", "pynput.mouse._darwin"]
    else:
        imports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
    return imports


def excluded_modules() -> list[str]:
    """Trim heavy optional dependencies that AutoTyper never imports.

    Only modules that are *not* required by PySide6's own bootstrap are listed
    here - removing ``shiboken6.Shiboken`` or the Qt plugins breaks startup.
    """
    return [
        "tkinter",
        "unittest",
        "pydoc",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
    ]


a = Analysis(  # noqa: F821 - provided by PyInstaller
    [str(PROJECT_ROOT / "build" / "launcher.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=asset_data(),
    hiddenimports=hidden_imports(),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules(),
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)  # noqa: F821 - provided by PyInstaller

exe = EXE(  # noqa: F821 - provided by PyInstaller
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoTyper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_for_platform(),
)

coll = COLLECT(  # noqa: F821 - provided by PyInstaller
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AutoTyper",
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821 - provided by PyInstaller
        coll,
        name="AutoTyper.app",
        icon=str(ASSETS / "autotyper.icns") if (ASSETS / "autotyper.icns").exists() else None,
        bundle_identifier="local.autotyper.app",
        version="1.0.0",
        info_plist={
            "CFBundleName": "AutoTyper",
            "CFBundleDisplayName": "AutoTyper",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.utilities",
            # macOS shows its own prompt when the user first triggers synthetic
            # input; these keys explain why in the Info.plist.
            "NSAppleEventsUsageDescription": (
                "AutoTyper types text into the app you choose. "
                "No data leaves your computer."
            ),
            "NSAccessibilityUsageDescription": (
                "AutoTyper needs Accessibility access to type text and to listen "
                "for its global start/pause/stop hotkeys."
            ),
            "NSHumanReadableCopyright": "MIT licensed",
        },
    )
