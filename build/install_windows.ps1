<#
.SYNOPSIS
    Install a built AutoTyper bundle for the current user.

.DESCRIPTION
    Copies ``dist\AutoTyper`` into ``%LOCALAPPDATA%\Programs\AutoTyper`` and
    creates:

    * a Desktop shortcut (optional with -NoDesktopShortcut)
    * a Start Menu shortcut
    * an Add/Remove Programs entry (per-user, no admin rights needed)

    A per-user install is used deliberately: AutoTyper needs no elevation to
    synthesise keystrokes, and installing under %LOCALAPPDATA% means the whole
    thing can be removed without administrator rights.

    Everything is verified after writing, so a partial copy or a shortcut that
    silently failed to be created is reported instead of assumed to work.

.PARAMETER SourceDir
    The built one-folder bundle. Defaults to ``dist\AutoTyper`` next to this
    script's parent directory.

.PARAMETER NoDesktopShortcut
    Skip the desktop shortcut (Start Menu and Add/Remove Programs are still
    created).

.PARAMETER Force
    Install even if a previous installation exists. The running executable is
    terminated first so files are not locked.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build\install_windows.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build\install_windows.ps1 -Force
#>
[CmdletBinding()]
param(
    [string] $SourceDir,
    [switch] $NoDesktopShortcut,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- resolve paths
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path $ProjectRoot 'dist\AutoTyper'
}
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)

$ExeName = 'AutoTyper.exe'
$SourceExe = Join-Path $SourceDir $ExeName
$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\AutoTyper'
$InstallExe = Join-Path $InstallDir $ExeName
$IconPath = Join-Path $ProjectRoot 'assets\autotyper.ico'

Write-Host '=== AutoTyper installer (per-user) ===' -ForegroundColor Cyan
Write-Host "Source : $SourceDir"
Write-Host "Target : $InstallDir"
Write-Host ''

# ------------------------------------------------------------------- validate
if (-not (Test-Path -LiteralPath $SourceExe)) {
    throw "Build not found: $SourceExe`nRun 'python -m PyInstaller build\autotyper.spec --noconfirm --clean' first."
}
if (-not (Test-Path -LiteralPath (Join-Path $SourceDir '_internal'))) {
    throw "'_internal' folder is missing from $SourceDir - the bundle looks incomplete."
}

# A running copy would lock AutoTyper.exe and make the copy fail halfway.
$running = @(Get-Process -Name 'AutoTyper' -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    if (-not $Force) {
        throw "AutoTyper is running (PID $($running.Id -join ', ')). Close it, or re-run with -Force."
    }
    Write-Host "Stopping running AutoTyper (PID $($running.Id -join ', ')) ..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Milliseconds 800
}

if (Test-Path -LiteralPath $InstallDir) {
    if (-not $Force) {
        Write-Host 'An existing installation was found; replacing it.' -ForegroundColor Yellow
    }
    Write-Host 'Removing the previous version ...'
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

# ----------------------------------------------------------------------- copy
Write-Host 'Copying application files ...'
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $SourceDir '*') -Destination $InstallDir -Recurse -Force

if (-not (Test-Path -LiteralPath $InstallExe)) {
    throw "Copy failed: $InstallExe was not created."
}
$copied = @(Get-ChildItem -LiteralPath $InstallDir -Recurse -File)
Write-Host ("Copied {0:N0} files." -f $copied.Count) -ForegroundColor Green

# ------------------------------------------------------------------ shortcuts
# WScript.Shell is the supported, dependency-free way to write .lnk files; the
# icon is taken from the packaged .ico inside the bundle so the shortcut shows
# the app icon even if the repo is later deleted.
$BundledIcon = Join-Path $InstallDir '_internal\autotyper\assets\autotyper.ico'
if (-not (Test-Path -LiteralPath $BundledIcon)) {
    $BundledIcon = $IconPath
}

function New-AppShortcut {
    <#
    .SYNOPSIS
        Create (or overwrite) a .lnk and return its path.
    #>
    param(
        [Parameter(Mandatory)][string] $LinkPath,
        [Parameter(Mandatory)][string] $TargetPath,
        [string] $WorkingDirectory,
        [string] $IconLocation
    )

    $parent = Split-Path -Parent $LinkPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($LinkPath)
        $shortcut.TargetPath = $TargetPath
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.Description = 'AutoTyper - type anywhere, with timing that feels human'
        if ($IconLocation -and (Test-Path -LiteralPath $IconLocation)) {
            $shortcut.IconLocation = "$IconLocation,0"
        }
        $shortcut.Save()
    }
    finally {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
    return $LinkPath
}

$created = @()

$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$startMenuLink = Join-Path $StartMenuDir 'AutoTyper.lnk'
$created += New-AppShortcut -LinkPath $startMenuLink -TargetPath $InstallExe `
    -WorkingDirectory $InstallDir -IconLocation $BundledIcon

if (-not $NoDesktopShortcut) {
    # Resolve the desktop through the shell so OneDrive-redirected desktops work.
    $desktopDir = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktopDir)) {
        $desktopDir = Join-Path $env:USERPROFILE 'Desktop'
    }
    $desktopLink = Join-Path $desktopDir 'AutoTyper.lnk'
    $created += New-AppShortcut -LinkPath $desktopLink -TargetPath $InstallExe `
        -WorkingDirectory $InstallDir -IconLocation $BundledIcon
}

foreach ($link in $created) {
    if (-not (Test-Path -LiteralPath $link)) {
        throw "Shortcut was not created: $link"
    }
    Write-Host "Shortcut: $link" -ForegroundColor Green
}

# ------------------------------------------------------- Add/Remove Programs
# HKCU (not HKLM) keeps the install per-user and needs no administrator rights.
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTyper'
$sizeKb = [int](($copied | Measure-Object -Property Length -Sum).Sum / 1KB)
$version = '1.0.0'

New-Item -Path $uninstallKey -Force | Out-Null
$uninstallProps = @{
    DisplayName     = 'AutoTyper'
    DisplayVersion  = $version
    Publisher       = 'AutoTyper contributors'
    DisplayIcon     = $InstallExe
    InstallLocation = $InstallDir
    UninstallString = ('powershell.exe -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $InstallDir 'uninstall.ps1'))
    NoModify        = 1
    NoRepair        = 1
    EstimatedSize   = $sizeKb
}
foreach ($name in $uninstallProps.Keys) {
    $value = $uninstallProps[$name]
    # An inline ``if`` expression is not a valid cmdlet argument in PowerShell,
    # so the registry type is chosen first and then passed by name.
    $type = if ($value -is [int]) { 'DWord' } else { 'String' }
    New-ItemProperty -Path $uninstallKey -Name $name -Value $value -PropertyType $type -Force |
        Out-Null
}
Write-Host 'Registered in Settings > Apps (per-user).' -ForegroundColor Green

# ------------------------------------------------------------- uninstaller
# Written next to the app so Remove-Programs has something to call.
$uninstallScript = Join-Path $InstallDir 'uninstall.ps1'
$uninstallBody = @'
# Remove the per-user AutoTyper install.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-Process -Name 'AutoTyper' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$targets = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AutoTyper.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AutoTyper.lnk')
)
foreach ($t in $targets) {
    if ($t -and (Test-Path -LiteralPath $t)) { Remove-Item -LiteralPath $t -Force }
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTyper' `
    -Recurse -Force -ErrorAction SilentlyContinue

# Delete the app itself last: this script lives inside $here.
Set-Location $env:TEMP
Remove-Item -LiteralPath $here -Recurse -Force
'@
Set-Content -LiteralPath $uninstallScript -Value $uninstallBody -Encoding UTF8
Write-Host "Uninstaller: $uninstallScript" -ForegroundColor Green

# ------------------------------------------------------------------ summary
Write-Host ''
Write-Host 'Install complete.' -ForegroundColor Cyan
Write-Host "  Executable : $InstallExe"
if (-not $NoDesktopShortcut) { Write-Host '  Desktop    : AutoTyper shortcut created' }
Write-Host '  Start Menu : AutoTyper'
Write-Host ''
Write-Host "Launch it from the desktop shortcut, or run:`n  `"$InstallExe`"" -ForegroundColor Gray
