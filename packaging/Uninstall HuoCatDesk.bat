@echo off
chcp 65001 >nul
echo ========================================
echo   HuoCatDesk 卸载
echo ========================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall
echo.
pause
