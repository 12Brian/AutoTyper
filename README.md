# AutoTyper

A polished, cross-platform desktop **auto-typing utility**. Paste or load text, press
Start (or a global hotkey), click into the target window, and AutoTyper types it out with
timing that feels human — so slow web forms don't drop characters and demos look natural.

Built with **Python 3.11+**, **PySide6** (Qt 6) for the interface and **pynput** for
keyboard simulation and global hotkeys. Ships as a standalone app for **Windows, macOS
and Linux** via **PyInstaller**.

**Developer:** Otachi

![AutoTyper icon](assets/autotyper-256.png)

---

## Table of contents

- [Features](#features)
- [Quick start](#quick-start)
- [Platform permissions & setup](#platform-permissions--setup)
- [Using AutoTyper](#using-autotyper)
- [Configuration & data files](#configuration--data-files)
- [Building standalone apps](#building-standalone-apps)
- [Project layout](#project-layout)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Design notes](#design-notes)
- [License](#license)

---

## Features

### Typing

- **Text editor** with character / word / line counters, plus **Load from file** (`*.txt`,
  `*.md`, …) and **Save to file**.
- **Faithful character handling** — newlines become <kbd>Enter</kbd>, tabs become
  <kbd>Tab</kbd>, and Unicode (accents, CJK, emoji) goes through the platform's Unicode
  input path rather than being silently dropped.
- **Robust file decoding** — UTF-8, UTF-8 with BOM, UTF-16 (Notepad's default) and legacy
  ANSI are all detected automatically; CRLF and CR are normalised to LF.
- **Repeat** the text N times (1–999) or **loop until stopped**, with a configurable delay
  between runs.

### Timing

- **Speed control** — slider *and* numeric field in **WPM** (10–1200), with the equivalent
  **characters per minute** shown alongside. One "word" is five characters, the standard
  typing-test convention.
- **Live time estimate** that updates as you drag sliders, including repeats and loop delays.
- **Human-like variability** (0–100 %) — randomised jitter plus slightly longer pauses at
  spaces, punctuation, tabs and newlines. This exists to keep slow input fields from
  dropping characters and to make demo typing look natural; it is not intended to defeat
  any detection system.
- **Configurable start countdown** (0–15 s, default 3 s) so you can focus the target window.

### Human behaviour

Real typing is measurable in ways a fixed delay cannot imitate. These models are **all off
by default**, so nothing changes until you opt in — and each one is independent.

- **Dwell time (key hold)** — a randomised press duration per keystroke, e.g. `40–110 ms`,
  instead of an instantaneous tap. The hold is *carved out of* the keystroke gap, not added
  on top of it, so the speed you set (and the WPM your target app measures) stays accurate.
  Holds vary key to key, and a panic stop mid-hold always releases the key.
- **Typos and error-correction loops** — a configurable share of characters (0–5 %) is
  mistyped to a physically adjacent key, then corrected: a short "oops" pause, a Backspace,
  and the right key retyped. The final text is still exact, and the count is reported in the
  activity log.
- **Bursty rhythm** — instead of independent noise on every keystroke, speed follows a
  slowly-varying "mood", so fast bursts are followed by slower recoveries. Average speed and
  overall spread are preserved; only the *correlation* between neighbouring keystrokes
  changes.
- **Pauses correlated with word difficulty** — pauses before long, unusual or mixed-case
  words (`antidisestablishmentarianism`, `passw0rd`, `getUserName`) stretch proportionally,
  the way a typist slows down to plan the next word.
- **No mouse movement, ever** — AutoTyper only synthesises keystrokes. It never moves the
  pointer or clicks, which keeps it non-destructive and squarely a keyboard tool.

### Control

- **Global hotkeys** that work while another app is focused:

  | Action | Default |
  | --- | --- |
  | Start typing | <kbd>F8</kbd> |
  | Pause / resume | <kbd>F7</kbd> |
  | **Emergency stop** | <kbd>F9</kbd> |

  > **Why function keys, not `Ctrl+Alt+T`?** If the target application ever
  > receives a leaked trigger letter while `Ctrl` is still held, that letter
  > becomes a shortcut (`Ctrl+T` = new tab, `Ctrl+V` = paste, `Ctrl+S` = save) and
  > silently destroys the text being typed. Function keys have no such meaning, so
  > a leak is harmless. AutoTyper also calls `settle()` before the first keystroke,
  > which releases modifiers, waits for the physical keys to come up, and clears
  > any queued residue.

- **Instant panic stop** — halts within one 20 ms sleep slice, no matter where you are,
  including during the countdown. <kbd>Esc</kbd> also stops a run while AutoTyper is focused.
- **Click-to-record** hotkey fields with validation and conflict detection (the panic key
  cannot be left unbound).

### Interface

- Light, dark and **follow-the-system** themes with a contrast-checked palette.
- **Status pill** (Idle / Counting down / Typing / Paused / Stopped / Completed / Error)
  that pulses while typing, plus a progress bar with `typed / total` counts.
- **Activity log** panel (capped at 200 lines) mirrored to a rotating log file.
- **Snippets manager** — save named snippets with their speed, variability, repeat and
  (optionally) hotkey settings; rename, reorder, update and delete them.
- **Permission banner** with platform-specific, numbered setup instructions.
- Keyboard-navigable, with tooltips and accessible names on the primary controls.

---

## Quick start

```bash
git clone https://github.com/12Brian/AutoTyper.git AutoTyper
cd AutoTyper

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m autotyper
```

Or install it as a command:

```bash
pip install -e .
autotyper
```

Then: paste text → pick a speed → press **Start typing** → click into the target window
(you get a 3-second countdown).


---

## Platform permissions & setup

AutoTyper synthesises keyboard input, which every desktop OS gates behind permissions.
It probes for access at startup and shows a banner with these steps if something is
missing.

### Windows

No setup required. Two caveats:

- **Elevation must match.** Windows blocks input from a lower-integrity process to a
  higher-integrity window. If your target app runs as administrator, run AutoTyper as
  administrator too (and vice versa).
- Some anti-cheat / remote-desktop tools block synthetic input entirely; close them.

### macOS

macOS requires explicit **Accessibility** permission:

1. Launch AutoTyper once (it will show a banner).
2. Open **System Settings → Privacy & Security → Accessibility**.
3. Enable the switch next to **AutoTyper** (use **+** to add it if it is not listed).
4. Also allow it under **Privacy & Security → Input Monitoring**.
5. **Quit and relaunch AutoTyper** — macOS only applies the grant on restart.

> **Running from source?** Grant the permission to your *terminal* (Terminal, iTerm2,
> VS Code) instead of to Python — the permission attaches to the parent process that
> spawns the interpreter.

Unsigned builds may need a right-click → **Open** the first time, or:

```bash
xattr -dr com.apple.quarantine /Applications/AutoTyper.app
```

### Linux

AutoTyper needs an **X11** session. `pynput` cannot reliably inject keystrokes or
register global hotkeys under native Wayland.

1. **Check your session:** `echo $XDG_SESSION_TYPE` → should print `x11`.
2. If it prints `wayland`, log out and choose an **"X11" / "Xorg"** session at the login
   screen. As a partial workaround, launch with `QT_QPA_PLATFORM=xcb` so Qt uses XWayland
   (hotkeys may still not work).
3. Install the X11 bindings if pynput complains about `Xlib`:

   ```bash
   # Debian / Ubuntu
   sudo apt install python3-xlib libxcb-cursor0 libxkbcommon-x11-0 \
                    libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-randr0 \
                    libxcb-render-util0 libxcb-image0 libxcb-xfixes0
   # Fedora
   sudo dnf install python3-xlib xcb-util-cursor libxkbcommon-x11
   # Arch
   sudo pacman -S python-xlib xcb-util-cursor libxkbcommon-x11
   ```

4. Make sure `DISPLAY` is set: `echo $DISPLAY` → e.g. `:0`.
5. Do not run AutoTyper as root; run it as your desktop user.

---

## Using AutoTyper

| Control | What it does |
| --- | --- |
| **Text to type** | Main editor. Newlines, tabs and Unicode are preserved. |
| **Load from file…** | Reads `.txt`/`.md` with automatic encoding detection. |
| **Save to file…** | Exports the editor contents as UTF-8 with LF newlines. |
| **Paste** | Inserts clipboard text with normalised newlines. |
| **Typing speed** | Slider + numeric WPM field. CPM and the time estimate update live. |
| **Human-like timing** | Variability slider plus a switch for pauses at spaces/punctuation. |
| **Code indentation** | Match the editor (plain text) or *Code editor* mode for Colab/VS Code. |
| **Repeat** | Type N times, or loop until stopped, with a delay between runs. |
| **Start typing** | Begins after the countdown (<kbd>Ctrl</kbd>+<kbd>Enter</kbd> in-app). |
| **Pause / Resume** | Halts at the next character boundary (<kbd>Ctrl</kbd>+<kbd>P</kbd>). |
| **Stop** | Immediate abort (<kbd>Ctrl</kbd>+<kbd>.</kbd> or <kbd>Esc</kbd> in-app). |
| **Snippets** | Save/load named text + settings combinations. |
| **Preferences** | Theme, default countdown, hotkey recording, platform diagnostics. |
| **Theme button** | Flips light ↔ dark. |

### Tips

- **Typing code into Colab, Jupyter, VS Code or an IDE?** Set **Code indentation** to
  *Code editor (Colab, VS Code)*. Those editors auto-indent after Enter, so typing the
  source's own indentation on top of theirs doubles it and each line drifts further right.
  This mode clears the editor's indent first, leaving exactly the indentation from your
  text. For Notepad, terminals and plain forms leave it on *Match the editor*.
- Start with **variability around 35 %** and **humanize pauses on** if a form drops
  characters; raise variability or lower the speed if it still struggles.
- For very slow legacy fields, try 60–120 WPM with variability 60+.
- The countdown is your friend — set 5 s if you need to alt-tab to another monitor.
- Bind a **panic key** you can hit without looking (<kbd>F9</kbd>, <kbd>Esc</kbd>, a
  thumb key). The banner warns you if it is unbound.


---

## Configuration & data files

Everything is stored as human-editable JSON in your per-user app-data directory:

| Platform | Location |
| --- | --- |
| Windows | `%APPDATA%\AutoTyper\` |
| macOS | `~/Library/Application Support/AutoTyper/` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/AutoTyper/` |

| File | Purpose |
| --- | --- |
| `settings.json` | Theme, default timing, hotkeys, last used profile, window geometry. |
| `profiles.json` | Saved snippets with their per-profile settings. |
| `activity.log` | Rotating activity log (512 KB × 3 backups). |

**Portable / testing override:** set `AUTOTYPER_DATA_DIR` to relocate *all* of the above:

```bash
AUTOTYPER_DATA_DIR=/media/usb/autotyper python -m autotyper
```

**Corruption safety:** writes are atomic (temp file + `os.replace`). If a document cannot
be parsed it is renamed to `<name>.corrupt-<timestamp>.json` and defaults are used, so a
crash or a bad hand-edit never loses the rest of your data.

---

## Building standalone apps

Build scripts create a virtual environment, install build dependencies, regenerate icons,
run the tests and invoke PyInstaller.

| Platform | Command | Output |
| --- | --- | --- |
| Windows | `build\build_windows.bat` | `dist\AutoTyper\AutoTyper.exe` |
| Windows (shareable) | `build\build_installer.ps1` | `dist\AutoTyper-Setup-1.0.0.exe` |
| macOS | `bash build/build_macos.sh` | `dist/AutoTyper.app` |
| Linux | `bash build/build_linux.sh` | `dist/AutoTyper/AutoTyper` + `.tar.gz` |
| Any (POSIX) | `bash build/build.sh` | Picks the right script automatically |

Or build directly:

```bash
pip install pyinstaller
python assets/make_icon.py                          # icons (once)
pyinstaller build/autotyper.spec --noconfirm --clean
```

**One-folder, not one-file.** PySide6 is large; a one-file bundle unpacks ~50 MB on every
launch (slow, and it breaks macOS signing). Distribute the folder or wrap it:

- **Windows per-user install (no admin rights):** after building, run

  ```powershell
  powershell -ExecutionPolicy Bypass -File build\install_windows.ps1
  ```

  This copies the bundle to `%LOCALAPPDATA%\Programs\AutoTyper` and creates a
  **Desktop shortcut**, a **Start Menu** entry, and a per-user **Apps & features**
  entry whose uninstall action calls the bundled `uninstall.ps1`. Add `-Force` to
  replace an existing install (it stops a running copy first), or
  `-NoDesktopShortcut` to skip the desktop icon.

  It installs per-user under `%LOCALAPPDATA%` on purpose: AutoTyper needs no
  elevation to type, so the whole app can be installed and removed without an
  administrator. For a machine-wide install or a shippable `.exe`, wrap
  `dist\AutoTyper\` in Inno Setup / NSIS / 7-Zip SFX instead.
- **macOS distribution:** sign and notarise —

  ```bash
  codesign --deep --force --options runtime \
    --sign "Developer ID Application: Your Name (TEAMID)" dist/AutoTyper.app
  xcrun notarytool submit AutoTyper.zip --keychain-profile <profile> --wait
  xcrun stapler staple dist/AutoTyper.app
  ```

  `build_macos.sh` signs automatically when `SIGN_IDENTITY` is set.
- **Linux distribution:** the `.tar.gz` contains a `.desktop` file and icon. You can also
  cut an AppImage or `.deb` with your tool of choice.

> **Cross-compilation is not supported** by PyInstaller. Build each platform on that
> platform (or in a matching CI runner/VM).

### Sharing it with someone else

The recommended way to hand AutoTyper to a friend is a **single `.exe` installer**:

```powershell
powershell -ExecutionPolicy Bypass -File build\build_installer.ps1
```

That produces `dist\AutoTyper-Setup-1.0.0.exe` (~33 MB). Your friend downloads one
file, double-clicks it, and gets a normal Windows install:

- installs **per-user** into `%LOCALAPPDATA%\Programs\AutoTyper` — no admin prompt
- **Desktop** shortcut (ticked by default) and a **Start Menu** group
- proper **Apps & features** entry, so it uninstalls like any other program
- optional "start with Windows" checkbox
- clean uninstall: removes the app, both shortcuts and the registry entry

Requires **Inno Setup 6** to compile (`winget install JRSoftware.InnoSetup`). The
script is `build\installer.iss`; `build\build_installer.ps1` finds the compiler,
keeps the version in sync, compiles, and fails loudly if no installer is produced.

**A portable ZIP** is also available if someone prefers not to install anything:

```powershell
powershell -ExecutionPolicy Bypass -File build\package_windows.ps1
```

→ `dist\AutoTyper-1.0.0-win64.zip` (~45 MB), containing a double-clickable
`Install AutoTyper.cmd` that only creates shortcuts.

Two caveats to mention when you share either one:

- **SmartScreen will warn on first run.** The build is not code-signed (certificates
  cost money annually), so Windows shows "Windows protected your PC". Click *More
  info → Run anyway*. The only real fix is buying a code-signing certificate and
  signing both `AutoTyper.exe` and the installer.
- **Windows only.** These contain Windows executables. macOS and Linux users need
  their own build from `build/build_macos.sh` / `build/build_linux.sh` on those
  platforms.

---

## Project layout

```
AutoTyper/
├── autotyper/
│   ├── __init__.py          # version
│   ├── __main__.py          # python -m autotyper
│   ├── app.py               # bootstrap: logging, settings, probe, window
│   ├── py.typed
│   ├── config/              # no Qt / no pynput imports
│   │   ├── models.py        # TypingSettings, HotkeySettings, AppSettings (+clamping)
│   │   ├── paths.py         # per-platform app-data locations
│   │   └── jsonstore.py     # atomic JSON read/write + corruption quarantine
│   ├── core/                # no Qt imports
│   │   ├── timing.py        # TimingEngine: WPM → Keystroke stream, estimates, formatting
│   │   ├── behaviour.py     # QWERTY adjacency, word difficulty, pause placement
│   │   ├── runner.py        # TypingRunner: state machine, pause/stop, dwell, progress
│   │   ├── keyboard.py      # KeyboardSink protocol + pynput backend
│   │   ├── hotkeys.py       # parse/validate/register global hotkeys
│   │   ├── text.py          # encoding detection, newline normalisation, previews
│   │   └── platform.py      # capability probe + remediation steps
│   ├── profiles/
│   │   ├── models.py        # Profile
│   │   ├── collection.py    # ProfileCollection (value type, unique names)
│   │   └── repository.py    # persistence
│   └── ui/
│       ├── theme.py         # light/dark tokens + QSS + palette
│       ├── main_window.py   # layout and controller wiring
│       ├── bridge.py        # QThread bridge (queued signals, throttled progress)
│       ├── settings_dialog.py
│       ├── profiles_dialog.py
│       ├── log_panel.py
│       └── widgets/         # cards, banner, hotkey recorder, status pill
├── assets/                  # make_icon.py + generated icons
├── build/                   # PyInstaller spec + per-platform scripts
├── tests/                   # pytest suite (headless)
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

---

## Development

```bash
pip install -r requirements-dev.txt

pytest                     # full suite, no display or real keyboard needed
pytest -q tests/test_timing.py
ruff check .
ruff format .
```

The test suite covers the timing engine, the run loop (including stop latency and
pause/resume), key dwell time, typo correction loops, burstiness, word-difficulty pauses,
profile persistence, hotkey parsing/validation, file decoding and the JSON
store. It runs headless: `NullKeyboard` stands in for pynput, and the runner takes an
injected RNG and clock.

Add a test when you change behaviour — the timing and persistence tests are what keep
"feels human" from silently becoming "types at 3× the requested speed".

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| **Text arrives upper-cased, or characters go missing and stray capitals appear** | The target window believed `Shift`/`Ctrl` was still held, so letters were sent as shortcuts. Fixed by `settle()` (which waits for the trigger keys to be released). If it persists, type into the window with the countdown instead of a hotkey, and avoid modifier-based bindings — use <kbd>F8</kbd>/<kbd>F9</kbd>. |
| "Keyboard access needed" banner on macOS | Grant Accessibility **and** Input Monitoring, then relaunch. Grant to your terminal if running from source. |
| Global hotkeys do nothing on Linux | You are probably on Wayland. Use an X11/Xorg session; install `python3-xlib`. |
| Hotkeys work but nothing is typed | Check AutoTyper and the target window run at the same elevation (Windows) and that no anti-cheat blocks input. |
| Characters dropped in a web form | Lower the speed and/or raise variability; try 60–120 WPM with "Pause naturally" on. |
| **Indentation drifts further right on each line** | You are typing code into an auto-indenting editor. Set **Code indentation → Code editor (Colab, VS Code)**. |
| Text arrives without line breaks | The target field is single-line — expected behaviour. |
| `QFontDatabase: Cannot find font directory` | Harmless, and only appears with `QT_QPA_PLATFORM=offscreen` (Qt ships no fonts for that plugin). |
| "Settings could not be saved" in the log | The app-data directory is read-only. Fix permissions or set `AUTOTYPER_DATA_DIR`. |
| App won't start over SSH | AutoTyper needs a graphical session (`DISPLAY`/`WAYLAND_DISPLAY`). |

Logs live at `activity.log` in the app-data directory; **Preferences → About** shows the
exact path plus the platform probe results.

---

## Design notes

A few decisions worth knowing if you plan to extend AutoTyper:

- **Layering.** `config`, `core.timing`, `core.runner`, `core.text` and `profiles` never
  import Qt, and `timing`/`runner` never import pynput. That is what makes the behaviour
  unit-testable without a display, and it keeps the UI a thin view.
- **Injected time and randomness.** `TimingEngine` takes a `random.Random`;
  `TypingRunner` takes a clock. Tests are therefore exact and deterministic, and a bug
  report can be reproduced from a seed.
- **Immediate stop.** Sleeping happens in 20 ms slices against a monotonic deadline, and
  pause/stop are plain `threading.Event` operations that the UI calls directly, so a panic
  press is never queued behind Qt events.
- **Progress coalescing.** Worker progress is throttled to ~30 Hz before crossing into the
  GUI thread — a 1200 WPM run would otherwise flood the event loop.
- **Value-type settings.** Every settings/profile dataclass clamps and normalises in
  `from_dict`/`normalized()`, so hand-edited or older JSON can never produce a zero-delay
  infinite loop or a negative countdown.
- **Dwell time is carved out of the gap, not added to it.** `TimingEngine` yields a
  `Keystroke(char, interval, hold, flight)` where `interval = hold + flight` is measured
  keydown-to-keydown. That keeps WPM, the live estimate and the target app's own typing meter
  in agreement, and it caps `hold` at 70 % of the gap so a release always precedes the next
  press. The runner sleeps the hold through the same interruptible slice loop as everything
  else and releases in a `finally`, so a panic stop cannot leave a key down.
- **Behaviour models are additive and default to zero.** Dwell time, typos, burstiness and
  difficulty weighting all derive from `TypingSettings` fields that default to `0`, and the
  engine only consults `core.behaviour` for the models that are switched on. Enabling nothing
  reproduces the original metronomic/jittered engine exactly, which is why the pre-existing
  test suite needed no changes.
- **Burstiness redistributes variance rather than adding it.** The correlated "mood" signal is
  variance-normalised and mixed with independent noise via `sqrt(1 - strength²)`, so raising
  burstiness changes *correlation*, not average speed or overall spread.
- **Pure behaviour helpers.** `core.behaviour` is deterministic (no RNG, no clock): QWERTY
  adjacency, word-difficulty scoring and the separator→difficulty map are all plain functions,
  so they are unit-testable on their own and the RNG stays in one place.
- **Atomic persistence.** `JsonStore` writes to a temp file and `os.replace`s it, then
  quarantines genuinely corrupt documents instead of overwriting them.

---

## License

MIT.
