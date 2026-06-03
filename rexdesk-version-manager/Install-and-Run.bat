@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo === Rexdesk Version Manager Setup ===
echo.

set "TOTAL_STEPS=7"
set "CURRENT_STEP=0"
set "REBUILD_EXE=Y"
call :show_stage 0 "Starting checks"

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
    call :show_stage 1 "Creating virtual environment (can take a few minutes)"
    echo This step can look idle on first run. Please wait...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    call :show_stage 1 "Virtual environment already exists"
)

call :show_stage 2 "Upgrading pip"
".venv\Scripts\python.exe" -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo Standard pip upgrade failed. Trying recovery...
    ".venv\Scripts\python.exe" -m ensurepip --upgrade
    ".venv\Scripts\python.exe" -m pip install --upgrade --ignore-installed pip
    if %errorlevel% neq 0 (
        echo Failed to repair pip in the virtual environment.
        echo You can delete the .venv folder and run this script again.
        pause
        exit /b 1
    )
)

call :show_stage 3 "Installing required packages"
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install required packages.
    pause
    exit /b 1
)

call :show_stage 4 "Installing optional drag-and-drop support"
".venv\Scripts\python.exe" -m pip install tkinterdnd2 >nul 2>&1

if exist "release\Rexdesk Version Manager.exe" (
    echo.
    choice /c YN /n /m "You already have a version. Reinstall/rebuild EXE? (Y/N): "
    if errorlevel 2 set "REBUILD_EXE=N"
)

if /i "!REBUILD_EXE!"=="Y" (
    call :show_stage 5 "Installing build tools"
    echo Installing/updating PyInstaller... this can take a minute.
    ".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
    if %errorlevel% neq 0 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )

    call :show_stage 6 "Building EXE"
    ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "Rexdesk Version Manager.spec"
    if %errorlevel% neq 0 (
        echo Failed to build EXE with PyInstaller.
        pause
        exit /b 1
    )

    if not exist "release" mkdir release
    copy /y "dist\Rexdesk Version Manager.exe" "release\Rexdesk Version Manager.exe" >nul
    if %errorlevel% neq 0 (
        echo Failed to copy EXE into release folder.
        pause
        exit /b 1
    )

    echo.
    echo EXE created at:
    echo %cd%\release\Rexdesk Version Manager.exe
    echo.
) else (
    call :show_stage 5 "Skipping EXE rebuild (using existing version)"
    call :show_stage 6 "EXE step skipped by choice"
)

call :show_stage 7 "Launching app"
echo Launching Rexdesk Version Manager...
".venv\Scripts\python.exe" ".\main.py"
if %errorlevel% neq 0 (
    echo.
    echo App exited with an error.
    pause
    exit /b 1
)

exit /b 0

:show_stage
set "CURRENT_STEP=%~1"
set "STATUS_TEXT=%~2"
set /a PERCENT=(CURRENT_STEP*100)/TOTAL_STEPS
set /a FILLED=PERCENT/10
set "BAR="
for /l %%A in (1,1,10) do (
    if %%A LEQ !FILLED! (
        set "BAR=!BAR!#"
    ) else (
        set "BAR=!BAR!-"
    )
)
echo [!BAR!] !PERCENT!%% - !STATUS_TEXT!
exit /b 0
