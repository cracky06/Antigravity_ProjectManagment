@echo off
setlocal
title Build Antigravity Manager
cd /d "%~dp0"

echo =============================================
echo   Antigravity Manager - Build Executable
echo =============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-App.ps1"

echo.
pause
