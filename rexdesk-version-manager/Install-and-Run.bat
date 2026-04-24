@echo off
setlocal
cd /d "%~dp0"

echo === Rexdesk Version Manager Setup ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python was not found on PATH.
    echo Install Python 3 from https://www.python.org/downloads/windows/
    echo During install, check "Add Python to PATH", then run this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install required packages.
    pause
    exit /b 1
)

echo Installing optional drag-and-drop support...
".venv\Scripts\python.exe" -m pip install tkinterdnd2 >nul 2>&1

echo.
echo Launching Rexdesk Version Manager...
".venv\Scripts\python.exe" ".\main.py"
if %errorlevel% neq 0 (
    echo.
    echo App exited with an error.
    pause
    exit /b 1
)
