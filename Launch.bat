@echo off
if exist "%~dp0Rexdesk Version Manager.exe" (
    start "" "%~dp0Rexdesk Version Manager.exe"
) else if exist "%~dp0rexdesk-version-manager\.venv\Scripts\python.exe" (
    cd /d "%~dp0rexdesk-version-manager"
    ".venv\Scripts\python.exe" main.py
) else (
    call "%~dp0Install-and-Run.bat"
)
