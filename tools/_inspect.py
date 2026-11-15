import pathlib

s = pathlib.Path("autotyper/ui/main_window.py").read_text(encoding="utf-8")
for token in ("QComboBox", "indent_combo", "indent_mode", "_select_combo"):
    print(f"{token:16} {s.count(token):3}x")
print("---- context ----")
for i, line in enumerate(s.splitlines(), 1):
    if "indent_combo" in line or "_select_combo(" in line or 'indent_mode' in line:
        print(i, line.strip())
