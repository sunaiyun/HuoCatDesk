# HuoCatDesk install/uninstall script (PowerShell). Called by the .bat launchers.
# Or directly: powershell -ExecutionPolicy Bypass -File install.ps1 [-Uninstall]
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'

$AppName      = 'HuoCatDesk'
$Version      = '0.1.0'
$Publisher    = 'HuoCatDesk'
$InstallDir   = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
$AppExe       = Join-Path $InstallDir 'huocatdesk.exe'
$SmDir        = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$SmLnk        = Join-Path $SmDir "$AppName.lnk"
$DeskLnk      = Join-Path $env:USERPROFILE "Desktop\$AppName.lnk"
$UninstallPs1 = Join-Path $InstallDir 'install.ps1'
$RegKey       = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\HuoCatDesk'

function New-Shortcut([string]$lnk, [string]$target, [string]$desc) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = $target
    $s.Description = $desc
    $s.WorkingDirectory = Split-Path $target
    $s.Save()
}

if ($Uninstall) {
    Write-Host "Uninstalling $AppName..." -ForegroundColor Yellow
    Remove-Item $SmLnk, $DeskLnk -ErrorAction SilentlyContinue
    Remove-Item $RegKey -ErrorAction SilentlyContinue
    Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "$AppName uninstalled." -ForegroundColor Green
    return
}

Write-Host "Installing $AppName..." -ForegroundColor Cyan
# 自动定位应用文件夹（兼容 HuoCatDesk / huocatdesk 大小写）
$Src = Get-ChildItem $PSScriptRoot -Directory -ErrorAction SilentlyContinue |
       Where-Object { Test-Path (Join-Path $_.FullName 'huocatdesk.exe') } |
       Select-Object -First 1 -ExpandProperty FullName
if (-not $Src) {
    Write-Error "App folder not found in $PSScriptRoot (make sure the package was fully extracted)"
    exit 1
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $Src '*') -Destination $InstallDir -Recurse -Force
Copy-Item $PSCommandPath $UninstallPs1 -Force

New-Shortcut $SmLnk $AppExe "$AppName P2P remote desktop"
try { New-Shortcut $DeskLnk $AppExe "$AppName P2P remote desktop" } catch {}

New-Item -Path $RegKey -Force | Out-Null
Set-ItemProperty $RegKey -Name DisplayName      -Value $AppName
Set-ItemProperty $RegKey -Name DisplayVersion   -Value $Version
Set-ItemProperty $RegKey -Name Publisher        -Value $Publisher
Set-ItemProperty $RegKey -Name InstallLocation  -Value $InstallDir
Set-ItemProperty $RegKey -Name UninstallString  -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$UninstallPs1`" -Uninstall"
Set-ItemProperty $RegKey -Name NoModify -Value 1 -Type DWord
Set-ItemProperty $RegKey -Name NoRepair  -Value 1 -Type DWord

Write-Host ''
Write-Host 'INSTALL COMPLETE' -ForegroundColor Green
Write-Host "  Directory : $InstallDir"
Write-Host "  Shortcuts : Start Menu + Desktop -> $AppName"
Write-Host "  Uninstall : Control Panel -> Programs -> $AppName, or run 'Uninstall $AppName.bat'"
