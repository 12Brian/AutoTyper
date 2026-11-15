# AutoTyper

Type anywhere — with timing that feels human.

Paste text, press **Start**, click into the window you want it typed into, and
AutoTyper types it out for you: at a speed you choose, with natural-looking
rhythm, pauses at punctuation, and optional realistic key-hold times.

Useful for filling long forms, pasting repetitive text into apps that block
clipboard paste, or demoing an interface without typing live.

---

## Install (one minute)

1. **Right-click the ZIP → Extract All.** Don't run anything from inside the
   ZIP preview — Windows can't run it from there.
2. Open the extracted folder and double-click **`Install AutoTyper.cmd`**.
3. Click **Yes** if Windows asks for confirmation.

That's it. You now have an **AutoTyper icon on your Desktop** and in the
**Start Menu**.

> **"Windows protected your PC"?** AutoTyper isn't code-signed (that costs
> money per year and this is a free tool), so SmartScreen may warn you on first
> run. Click **More info → Run anyway**. If you prefer, you can skip the
> installer entirely and just double-click `AutoTyper.exe` in the folder.

**No admin rights needed**, and nothing is written to Program Files.

---

## Use it

1. Paste or type your text into the big box.
2. Pick a speed (300 WPM is a comfortable human pace).
3. Press **Start typing** (or <kbd>F8</kbd> anywhere).
4. You get a 3-second countdown — click into the target window during it.

### Hotkeys (work even when AutoTyper is in the background)

| Key | Action |
| --- | --- |
| <kbd>F8</kbd> | Start typing |
| <kbd>F7</kbd> | Pause / resume |
| <kbd>F9</kbd> | **Stop immediately** |

<kbd>F9</kbd> is the panic key — it halts within about 20 ms. Memorise it
before your first run.

### The settings that matter

- **Speed / variability** — start at 300 WPM and 35 % variability. If a slow
  web form drops characters, lower the speed or raise the variability.
- **Key hold (dwell time)** — set something like `40`–`110` ms if you want
  keystrokes to look physically held rather than instant. This doesn't slow
  your chosen speed down; the hold is carved out of the gap between keys.
- **Typos** — 0 % by default. Setting 1–3 % makes AutoTyper occasionally make a
  slip and correct it with Backspace, the way a person does. The final text is
  always exact.
- **Burstiness / hard-word pauses** — makes the rhythm come in bursts and pause
  before long or unusual words. Both off by default.

Everything except the countdown is edited on the main window and saved into
settings, so it persists between launches.

---

## Where your data lives

Everything stays on your computer, in
`%APPDATA%\AutoTyper\` (`settings.json`, `profiles.json`, `activity.log`).

**AutoTyper has no internet access**, no telemetry, no accounts and no cloud
sync. It only synthesises keystrokes into whatever window you focus.

---

## Uninstall

Either:

- **Settings → Apps → AutoTyper → Uninstall**, or
- run **`Uninstall.ps1`** in the application folder.

Then delete the AutoTyper folder. Your `%APPDATA%\AutoTyper` settings are kept
so a reinstall remembers your preferences — delete that folder too if you want
a completely clean removal.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Nothing types | AutoTyper types into the **focused** window. Make sure you clicked into the target before the countdown ends. |
| Characters get dropped | Lower the speed, or raise variability to 60+. This is exactly what the variability setting is for. |
| It types into the wrong window | Don't click anything during typing — it follows your focus, not a fixed window. |
| Wrong indentation in a code editor | Set **Indentation → Code editor (Colab, VS Code)** so it clears the editor's auto-indent. |
| Hotkeys don't work | Another app may have claimed <kbd>F8</kbd>/<kbd>F7</kbd>/<kbd>F9</kbd>. Change them in **Preferences → Hotkeys**. |

---

MIT licensed. Built with Python, PySide6 and pynput.
