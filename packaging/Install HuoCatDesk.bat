@echo off
chcp 65001 >nul
echo ========================================
echo   HuoCatDesk 安装
echo ========================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
