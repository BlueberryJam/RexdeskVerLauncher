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

".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
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

echo Building Rexdesk Version Manager...
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "Rexdesk Version Manager.spec"
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
