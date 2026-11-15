<#
.SYNOPSIS
    Install AutoTyper from a shared folder (per-user, no admin rights).

.DESCRIPTION
    Creates a Desktop shortcut, a Start Menu shortcut and an entry in
    Settings > Apps that points back at this folder.

    This is the "portable" installer shipped inside the shareable ZIP. It does
    *not* copy the ~113 MB payload: the shortcuts target the executable in this
    folder, so the folder can live on the Desktop, in Documents, or on a USB
    stick. Moving the folder afterwards breaks the shortcuts - re-run this
    script to fix them.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Here 'AutoTyper.exe'
$Icon = Join-Path $Here '_internal\autotyper\assets\autotyper.ico'

Write-Host ''
Write-Host '=== AutoTyper setup ===' -ForegroundColor Cyan
Write-Host "Folder: $Here"
Write-Host ''

if (-not (Test-Path -LiteralPath $Exe)) {
    Write-Host 'ERROR: AutoTyper.exe is missing from this folder.' -ForegroundColor Red
    Write-Host 'Extract the whole ZIP first, then run this installer again.' -ForegroundColor Yellow
    exit 1
}

function New-Shortcut {
    param([string] $LinkPath)
    $parent = Split-Path -Parent $LinkPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($LinkPath)
        $shortcut.TargetPath = $Exe
        $shortcut.WorkingDirectory = $Here
        $shortcut.Description = 'AutoTyper - type anywhere, with timing that feels human'
        if (Test-Path -LiteralPath $Icon) { $shortcut.IconLocation = "$Icon,0" }
        $shortcut.Save()
    }
    finally {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}

# --------------------------------------------------------------- shortcuts
Write-Host 'Creating shortcuts ...'
New-Shortcut -LinkPath (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AutoTyper.lnk')

$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) {
    $desktop = Join-Path $env:USERPROFILE 'Desktop'
}
$desktopLink = Join-Path $desktop 'AutoTyper.lnk'
New-Shortcut -LinkPath $desktopLink
Write-Host "  Desktop    : $desktopLink" -ForegroundColor Green
Write-Host '  Start Menu : AutoTyper' -ForegroundColor Green

# ------------------------------------------------- Settings > Apps entry
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTyper'
New-Item -Path $key -Force | Out-Null
$props = [ordered]@{
    DisplayName     = 'AutoTyper'
    DisplayVersion  = '1.0.0'
    Publisher       = 'Otachi'
    DisplayIcon     = $Exe
    InstallLocation = $Here
    UninstallString = ('powershell.exe -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $Here 'Uninstall.ps1'))
    NoModify        = 1
    NoRepair        = 1
}
foreach ($name in $props.Keys) {
    $value = $props[$name]
    $type = if ($value -is [int]) { 'DWord' } else { 'String' }
    New-ItemProperty -Path $key -Name $name -Value $value -PropertyType $type -Force | Out-Null
}
Write-Host '  Added to Settings > Apps' -ForegroundColor Green

Write-Host ''
Write-Host 'Done. Launch AutoTyper from your Desktop or the Start Menu.' -ForegroundColor Cyan
Write-Host 'Press F8 to start typing, F9 to stop.' -ForegroundColor Gray
Write-Host ''
