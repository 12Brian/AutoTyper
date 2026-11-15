@echo off
REM ---------------------------------------------------------------------------
REM Install AutoTyper for the current user (no admin rights required).
REM
REM Creates a Desktop shortcut, a Start Menu entry and an entry in
REM Settings > Apps, pointing at this folder. Keep this folder where it is, or
REM move the whole folder together - the shortcut follows it.
REM
REM Usage:  double-click "Install AutoTyper.cmd"
REM ---------------------------------------------------------------------------
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
endlocal
