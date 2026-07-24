@echo off
setlocal
cd /d "%~dp0rexdesk-version-manager"
if exist "..\Rexdesk Version Manager.exe" (
    start "" "..\Rexdesk Version Manager.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" ".\main.py"
) else (
    echo Rexdesk Version Manager is not set up yet.
    echo.
    echo Please run: rexdesk-version-manager\Install-and-Run.bat
    echo.
    pause
)
