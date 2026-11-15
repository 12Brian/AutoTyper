import pathlib

root = pathlib.Path(".")
# Verify the indent wiring landed correctly.
s = (root / "autotyper/ui/main_window.py").read_text(encoding="utf-8")
checks = {
    "QComboBox imported": "    QComboBox,\n" in s,
    "combo created": "self.indent_combo = QComboBox()" in s,
    "mode read": "indent_mode=str(self.indent_combo.currentData())" in s,
    "mode restored": "_select_combo(self.indent_combo, typing.indent_mode)" in s,
    "helper defined": "def _select_combo(" in s,
    "signals blocked": "            self.indent_combo,\n        ):" in s,
}
for name, ok in checks.items():
    print(f"{'OK  ' if ok else 'FAIL'} {name}")

# Every module must at least parse.
import ast

bad = []
for path in root.rglob("*.py"):
    if any(part in {".venv", "dist", "build", "__pycache__"} for part in path.parts):
        continue
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        bad.append(f"{path}: {exc}")
print("parse failures:", bad or "none")
