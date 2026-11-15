# Assemble a shareable AutoTyper ZIP.
#
# Copies the built bundle plus the friend-facing installer/readme into a clean
# folder tree and zips it, so the recipient extracts one folder and double-clicks
# "Install AutoTyper.cmd".
#
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File build\package_windows.ps1
#
# Output: dist\AutoTyper-1.0.0-win64.zip

[CmdletBinding()]
param(
    [string] $SourceDir,
    [string] $Version = '1.0.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path $ProjectRoot 'dist\AutoTyper'
}
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)

$ShareDir = Join-Path $ScriptRoot 'share'
$BundleName = "AutoTyper-$Version-win64"
$StageDir = Join-Path $ProjectRoot "dist\$BundleName"
$ZipPath = Join-Path $ProjectRoot "dist\$BundleName.zip"

Write-Host '=== Packaging AutoTyper for sharing ===' -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $SourceDir 'AutoTyper.exe'))) {
    throw "No build found in $SourceDir. Run the PyInstaller build first."
}

foreach ($required in @('Install AutoTyper.cmd', 'install.ps1', 'Uninstall.ps1', 'README.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ShareDir $required))) {
        throw "Missing share asset: $required"
    }
}

# ---------------------------------------------------------------- stage
if (Test-Path -LiteralPath $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

Write-Host 'Copying the built application ...'
Copy-Item -Path (Join-Path $SourceDir '*') -Destination $StageDir -Recurse -Force

# Drop a stale uninstaller from the build folder *before* adding the share
# assets: Windows paths are case-insensitive, so removing ``uninstall.ps1``
# afterwards would also delete the packaged ``Uninstall.ps1``.
$stale = Join-Path $StageDir 'uninstall.ps1'
if (Test-Path -LiteralPath $stale) { Remove-Item -LiteralPath $stale -Force }

Write-Host 'Adding installer and documentation ...'
Copy-Item -Path (Join-Path $ShareDir '*') -Destination $StageDir -Force

# Strip caches that should never be redistributed.
Get-ChildItem -LiteralPath $StageDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$files = @(Get-ChildItem -LiteralPath $StageDir -Recurse -File)
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
Write-Host ("Staged {0:N0} files ({1:N1} MB)." -f $files.Count, ($bytes / 1MB)) -ForegroundColor Green

foreach ($expected in @('AutoTyper.exe', 'Install AutoTyper.cmd', 'README.txt', 'install.ps1', 'Uninstall.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $StageDir $expected))) {
        throw "Staging incomplete: $expected is missing."
    }
}

# ------------------------------------------------------------------ zip
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }

Write-Host 'Compressing ...'
Add-Type -AssemblyName System.IO.Compression.FileSystem
# Optimal, not Fastest: friends download this, so a smaller file wins.
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $StageDir,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
)

if (-not (Test-Path -LiteralPath $ZipPath)) { throw 'ZIP was not created.' }
$zipMb = (Get-Item -LiteralPath $ZipPath).Length / 1MB
Write-Host ''
Write-Host 'Package ready.' -ForegroundColor Cyan
Write-Host ("  ZIP    : {0}" -f $ZipPath)
Write-Host ("  Size   : {0:N1} MB" -f $zipMb)
Write-Host ("  Folder : {0} (also left unpacked for inspection)" -f $StageDir)
