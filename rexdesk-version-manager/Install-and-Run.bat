@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo =============================================
echo   Rexdesk Version Manager - Setup ^& Launch
echo =============================================
echo.

:: Python version used for the manual-download fallback
set "PY_VER=3.12.7"

set "TOTAL_STEPS=9"
set "REBUILD_EXE=Y"
call :show_stage 0 "Starting setup"

:: ════════════════════════════════════════════════════════════════════════════
:: Step 1 — Python
:: ════════════════════════════════════════════════════════════════════════════
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Python 3 was not found on PATH.
    echo.
    choice /c YN /n /m "Install Python 3 automatically? (Y/N): "
    if !errorlevel! equ 2 (
        echo.
        echo Please install Python 3 manually:
        echo   https://www.python.org/downloads/windows/
        echo Check "Add Python to PATH" during install, then run this file again.
        echo.
        pause
        exit /b 1
    )
    call :install_python
    if !errorlevel! neq 0 (
        pause
        exit /b 1
    )
)
call :show_stage 1 "Python is ready"

:: ════════════════════════════════════════════════════════════════════════════
:: Step 2 — Virtual environment
:: ════════════════════════════════════════════════════════════════════════════
if not exist ".venv\Scripts\python.exe" (
    call :show_stage 2 "Creating virtual environment"
    echo This may look idle for a moment - please wait...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    call :show_stage 2 "Virtual environment already exists"
)

:: ════════════════════════════════════════════════════════════════════════════
:: Step 3 — Upgrade pip
:: ════════════════════════════════════════════════════════════════════════════
call :show_stage 3 "Upgrading pip"
".venv\Scripts\python.exe" -m pip install --upgrade pip
if !errorlevel! neq 0 (
    echo Standard pip upgrade failed. Trying recovery...
    ".venv\Scripts\python.exe" -m ensurepip --upgrade
    ".venv\Scripts\python.exe" -m pip install --upgrade --ignore-installed pip
    if !errorlevel! neq 0 (
        echo Failed to repair pip.
        echo Delete the .venv folder and run this file again.
        pause
        exit /b 1
    )
    echo pip repaired successfully.
)

:: ════════════════════════════════════════════════════════════════════════════
:: Step 4 — Required packages
:: ════════════════════════════════════════════════════════════════════════════
call :show_stage 4 "Installing required packages"
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if !errorlevel! neq 0 (
    echo Failed to install required packages.
    pause
    exit /b 1
)

:: ════════════════════════════════════════════════════════════════════════════
:: Step 5 — Optional drag-and-drop support
:: ════════════════════════════════════════════════════════════════════════════
".venv\Scripts\python.exe" -c "import tkinterdnd2" >nul 2>&1
if !errorlevel! equ 0 (
    call :show_stage 5 "Drag-and-drop support already installed"
) else (
    echo.
    choice /c YN /n /m "Install optional drag-and-drop support? (Y/N): "
    if !errorlevel! equ 1 (
        call :show_stage 5 "Installing drag-and-drop support"
        ".venv\Scripts\python.exe" -m pip install tkinterdnd2 >nul 2>&1
        if !errorlevel! equ 0 (
            echo Drag-and-drop support installed.
        ) else (
            echo Could not install drag-and-drop support ^(optional - skipped^).
        )
    ) else (
        call :show_stage 5 "Drag-and-drop support skipped"
    )
)

:: ════════════════════════════════════════════════════════════════════════════
:: Steps 6-7 — Build EXE (optional)
:: ════════════════════════════════════════════════════════════════════════════
if exist "..\Rexdesk Version Manager.exe" (
    echo.
    choice /c YN /n /m "An EXE already exists. Rebuild it? (Y/N): "
    if !errorlevel! equ 2 set "REBUILD_EXE=N"
)

if /i "!REBUILD_EXE!"=="Y" (
    call :show_stage 6 "Installing build tools"
    echo Installing/updating PyInstaller...
    ".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
    if !errorlevel! neq 0 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )

    call :show_stage 7 "Building EXE"
    ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "Rexdesk Version Manager.spec"
    if !errorlevel! neq 0 (
        echo Build failed.
        pause
        exit /b 1
    )

    copy /y "dist\Rexdesk Version Manager.exe" "..\Rexdesk Version Manager.exe" >nul
    if !errorlevel! neq 0 (
        echo Failed to copy EXE to the RexdeskVerLauncher folder.
        pause
        exit /b 1
    )
    echo EXE created: %cd%\..\Rexdesk Version Manager.exe
) else (
    call :show_stage 6 "EXE rebuild skipped"
    call :show_stage 7 "Using existing EXE"
)

:: ════════════════════════════════════════════════════════════════════════════
:: Step 8 — Create launch file in parent folder
:: ════════════════════════════════════════════════════════════════════════════
call :show_stage 8 "Creating launch file"
call :create_launch_file

:: ════════════════════════════════════════════════════════════════════════════
:: Step 9 — Launch the app
:: ════════════════════════════════════════════════════════════════════════════
call :show_stage 9 "Launching Rexdesk Version Manager"
echo.
".venv\Scripts\python.exe" ".\main.py"
if !errorlevel! neq 0 (
    echo.
    echo App exited with an error.
    pause
    exit /b 1
)

exit /b 0


:: ════════════════════════════════════════════════════════════════════════════
:show_stage
set /a _PCT=(%~1*100)/!TOTAL_STEPS!
set /a _FILL=!_PCT!/10
set "_BAR="
for /l %%A in (1,1,10) do (
    if %%A LEQ !_FILL! (
        set "_BAR=!_BAR!#"
    ) else (
        set "_BAR=!_BAR!-"
    )
)
echo [!_BAR!] !_PCT!%% - %~2
exit /b 0


:: ════════════════════════════════════════════════════════════════════════════
:install_python
call :show_stage 1 "Installing Python 3"
echo.

:: Try Windows Package Manager (winget) — available on Win 10 1809+ / Win 11
winget --version >nul 2>&1
if !errorlevel! equ 0 (
    echo Trying Windows Package Manager ^(winget^)...
    winget install --id Python.Python.3 --accept-source-agreements --accept-package-agreements --silent
    if !errorlevel! equ 0 (
        call :refresh_path
        call :find_python_in_appdata
        python --version >nul 2>&1
        if !errorlevel! equ 0 (
            echo Python installed via winget.
            exit /b 0
        )
    )
    echo winget did not finish cleanly or PATH not updated - trying download...
)

:: Fallback: download installer from python.org
set "_PY_URL=https://www.python.org/ftp/python/!PY_VER!/python-!PY_VER!-amd64.exe"
set "_PY_INST=%TEMP%\python-setup-!PY_VER!.exe"

echo Downloading Python !PY_VER! ^(64-bit^) from python.org...
powershell -NoProfile -Command ^
    "try { Invoke-WebRequest -Uri '!_PY_URL!' -OutFile '!_PY_INST!' -UseBasicParsing; exit 0 } catch { Write-Host ('Download error: ' + $_.Exception.Message); exit 1 }"
if !errorlevel! neq 0 (
    echo.
    echo Could not download Python automatically.
    echo Please install manually: https://www.python.org/downloads/windows/
    echo Check "Add Python to PATH", then run this file again.
    exit /b 1
)

echo Running installer ^(this may take a minute^)...
"!_PY_INST!" /passive InstallAllUsers=0 PrependPath=1 Include_test=0
set "_RC=!errorlevel!"
del /f /q "!_PY_INST!" >nul 2>&1
if !_RC! neq 0 (
    echo Python installer exited with code !_RC!.
    echo It may have partially installed or need a UAC prompt.
    exit /b 1
)

call :refresh_path
call :find_python_in_appdata

python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo Python was installed but is not available in this session yet.
    echo Please close this window and run this file again.
    exit /b 1
)
echo Python !PY_VER! installed successfully.
exit /b 0


:: ════════════════════════════════════════════════════════════════════════════
:refresh_path
:: Read the User PATH from the registry so new installs are visible
for /f "usebackq delims=" %%A in (
    `powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('PATH','User')"`
) do (
    if not "%%A"=="" set "PATH=%%A;!PATH!"
)
exit /b 0


:: ════════════════════════════════════════════════════════════════════════════
:find_python_in_appdata
:: If the Python exe landed in AppData but PATH refresh did not pick it up,
:: add the folder manually so python is usable in this session.
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PATH=%%D;%%D\Scripts;!PATH!"
)
exit /b 0


:: ════════════════════════════════════════════════════════════════════════════
:create_launch_file
:: Resolve the parent folder (one level above this script)
pushd "%~dp0.."
set "_LAUNCH_DIR=%CD%"
popd
set "_LAUNCH=!_LAUNCH_DIR!\Launch Rexdesk Version Manager.bat"

(
    echo @echo off
    echo setlocal
    echo cd /d "%%~dp0rexdesk-version-manager"
    echo if exist "..\Rexdesk Version Manager.exe" ^(
    echo     start "" "..\Rexdesk Version Manager.exe"
    echo ^) else if exist ".venv\Scripts\pythonw.exe" ^(
    echo     start "" ".venv\Scripts\pythonw.exe" ".\main.py"
    echo ^) else ^(
    echo     echo Rexdesk Version Manager is not set up yet.
    echo     echo.
    echo     echo Please run: rexdesk-version-manager\Install-and-Run.bat
    echo     echo.
    echo     pause
    echo ^)
) > "!_LAUNCH!"

if !errorlevel! equ 0 (
    echo Launch file created: !_LAUNCH!
) else (
    echo Warning: could not create launch file in parent folder.
)
exit /b 0
