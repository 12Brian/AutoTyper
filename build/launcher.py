"""PyInstaller entry point for AutoTyper.

PyInstaller runs the entry script as ``__main__`` with no parent package, so
``autotyper/__main__.py`` (which uses relative imports) cannot be used directly.
This module imports the package absolutely and delegates to its ``main()``.
"""

from __future__ import annotations

import multiprocessing
import sys

from autotyper.app import main

if __name__ == "__main__":
    # Required for frozen builds on Windows: without it, any child process would
    # re-execute the whole GUI instead of starting fresh.
    multiprocessing.freeze_support()
    sys.exit(main())
