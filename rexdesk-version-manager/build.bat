@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
if %errorlevel% neq 0 (
    echo Standard pip upgrade failed, attempting recovery...
    rem  This path handles "no RECORD file was found for pip" — a corrupted
    rem  pip install in the venv. pip's own recommended workaround is to
    rem  reinstall ignoring the existing on-disk install.
    ".venv\Scripts\python.exe" -m pip install --upgrade --ignore-installed --no-deps pip >nul 2>&1
    if %errorlevel% neq 0 (
        echo Could not upgrade pip; continuing with the bundled version.
    )
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt >nul
if %errorlevel% neq 0 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install pyinstaller >nul
if %errorlevel% neq 0 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller was not found in the virtual environment.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import tkinterdnd2" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing tkinterdnd2 for drag-drop support...
    ".venv\Scripts\python.exe" -m pip install tkinterdnd2
)

".venv\Scripts\python.exe" -c "import PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Pillow for product logos...
    ".venv\Scripts\python.exe" -m pip install pillow
)

".venv\Scripts\python.exe" -c "import fitz" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyMuPDF for SVG logos...
    ".venv\Scripts\python.exe" -m pip install pymupdf
)

rem  Close any previously-built copy of the EXE so it doesn't hold its
rem  files (especially the localpycs subfolder) open.
taskkill /f /im "Rexdesk Version Manager.exe" >nul 2>&1

rem  Wipe build/ and dist/ ourselves with retries. PyInstaller's own
rem  --clean uses shutil.rmtree which trips over OneDrive / antivirus
rem  locks and aborts the build (WinError 5: Access is denied).
echo Cleaning previous build artifacts...
for %%D in (build dist) do (
    if exist "%%D" (
        for /l %%i in (1,1,8) do (
            if exist "%%D" (
                rmdir /s /q "%%D" >nul 2>&1
                if exist "%%D" timeout /t 1 /nobreak >nul 2>&1
            )
        )
        if exist "%%D" (
            echo Warning: %%D is still locked.
            echo   Likely cause: OneDrive sync, antivirus, or a running EXE.
            echo   Pause OneDrive sync for this folder and try again, or move
            echo   the project out of OneDrive ^(e.g. to C:\dev\^).
            pause
            exit /b 1
        )
    )
)

echo Building Rexdesk Version Manager...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm "Rexdesk Version Manager.spec"
if %errorlevel% neq 0 (
    echo.
    echo Build failed.
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
echo Build complete.
echo Portable EXE: %cd%\release\Rexdesk Version Manager.exe
echo.
echo Tip: run build-installer.bat to create a Windows installer package.
pause
