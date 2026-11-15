# Compile the single-file AutoTyper installer with Inno Setup.
#
# Requires Inno Setup 6 (``winget install JRSoftware.InnoSetup``) and an existing
# PyInstaller build in dist\AutoTyper\.
#
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File build\build_installer.ps1

[CmdletBinding()]
param(
    [string] $Version = '1.0.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$DistDir = Join-Path $ProjectRoot 'dist'
$IssFile = Join-Path $ScriptRoot 'installer.iss'

Write-Host '=== Building the AutoTyper installer ===' -ForegroundColor Cyan

# ---------------------------------------------------------------- prerequisites
if (-not (Test-Path -LiteralPath (Join-Path $DistDir 'AutoTyper\AutoTyper.exe'))) {
    throw "No PyInstaller build in dist\AutoTyper. Build it first (pyinstaller build\autotyper.spec)."
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup"
}
Write-Host "Compiler: $iscc"

# Keep the script's version in sync with the requested one so the filename matches.
$issText = Get-Content -LiteralPath $IssFile -Raw
$patched = $issText -replace '(#define\s+AppVersion\s+")[^"]*(")', "`${1}$Version`${2}"
if ($patched -ne $issText) {
    Set-Content -LiteralPath $IssFile -Value $patched -Encoding UTF8 -NoNewline
    Write-Host "Version set to $Version"
}

# ---------------------------------------------------------------------- compile
# Delete a previous artifact so a failed compile cannot leave a stale installer
# that looks like it succeeded.
$expected = Join-Path $DistDir "AutoTyper-Setup-$Version.exe"
if (Test-Path -LiteralPath $expected) { Remove-Item -LiteralPath $expected -Force }

Write-Host 'Compiling ...'
& $iscc $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $expected)) {
    throw "Expected installer was not produced: $expected"
}

$sizeMb = (Get-Item -LiteralPath $expected).Length / 1MB
Write-Host ''
Write-Host 'Installer ready.' -ForegroundColor Cyan
Write-Host ("  File : {0}" -f $expected)
Write-Host ("  Size : {0:N1} MB" -f $sizeMb)
