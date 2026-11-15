@echo off
REM ---------------------------------------------------------------------------
REM Build a standalone AutoTyper for Windows.
REM
REM Requires Python 3.11+ on PATH. Creates a local virtual environment, installs
REM the build dependencies and produces dist\AutoTyper\AutoTyper.exe.
REM
REM Usage:  build\build_windows.bat
REM ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion
pushd "%~dp0.."

set VENV=.venv
set PY=python

echo === AutoTyper Windows build ===
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: python was not found on PATH. Install Python 3.11+ and retry.
    popd & exit /b 1
)

if not exist "%VENV%" (
    echo Creating virtual environment in %VENV% ...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo ERROR: could not create the virtual environment.
        popd & exit /b 1
    )
)

call "%VENV%\Scripts\activate.bat"

echo Installing dependencies ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERROR: dependency installation failed.
    popd & exit /b 1
)

echo Generating icons ...
python assets\make_icon.py

echo Running tests ...
python -m pytest -q
if errorlevel 1 (
    echo WARNING: tests failed. Fix them before shipping a release.
)

echo Building the executable ...
pyinstaller build\autotyper.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    popd & exit /b 1
)

echo.
echo Build complete: dist\AutoTyper\AutoTyper.exe
echo Create a single-file installer with Inno Setup or 7-Zip if you need one.
popd
endlocal
