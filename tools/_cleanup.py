"""Delete temporary helper scripts created during debugging.

Run with ``python tools/_cleanup.py`` and then delete this file too.
"""

import pathlib

for name in ("_patch_indent.py", "_inspect.py", "_verify_indent.py", "_cleanup.py"):
    path = pathlib.Path("tools") / name
    if path.exists():
        path.unlink()
        print("removed", path)

# A stray single-letter file was created by a failed heredoc in PowerShell.
for name in ("c", "p", "e"):
    path = pathlib.Path(name)
    if path.exists() and path.is_file() and path.stat().st_size < 64:
        path.unlink()
        print("removed stray", name)
