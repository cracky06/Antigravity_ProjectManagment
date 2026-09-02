@echo off
title Antigravity Manager
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" antigravity_manager.py
) else (
    python antigravity_manager.py
)

pause

