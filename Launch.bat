@echo off
cd /d "%~dp0rexdesk-version-manager"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    call "Install-and-Run.bat"
)
