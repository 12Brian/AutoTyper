# Uninstall AutoTyper (per-user).
# Removes the shortcuts and the Settings > Apps entry. The application folder
# itself is left in place - delete it manually if you no longer want it.

$ErrorActionPreference = 'SilentlyContinue'

Get-Process -Name 'AutoTyper' | Stop-Process -Force
Start-Sleep -Milliseconds 400

$links = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AutoTyper.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AutoTyper.lnk')
)
foreach ($link in $links) {
    if ($link -and (Test-Path -LiteralPath $link)) { Remove-Item -LiteralPath $link -Force }
}

Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTyper' -Recurse -Force

Write-Host 'AutoTyper has been removed from the Desktop, Start Menu and Settings > Apps.'
Write-Host 'You can now delete the application folder.'
