@echo off
cd /d "%~dp0"

python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo.
        echo Failed to install PyInstaller. Make sure Python is on your PATH.
        pause
        exit /b 1
    )
)

python -c "import tkinterdnd2" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing tkinterdnd2 for drag-drop support...
    python -m pip install tkinterdnd2
)

python -c "import PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Pillow for product logos...
    python -m pip install pillow
)

python -c "import fitz" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyMuPDF for SVG logos...
    python -m pip install pymupdf
)

echo Building Rexdesk Version Manager...
python -m PyInstaller "Rexdesk Version Manager.spec"
if %errorlevel% neq 0 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)
echo.
echo Closing any running instances...
taskkill /f /im "Rexdesk Version Manager.exe" >nul 2>&1
echo.
echo Copying to Rexdesk Vershons folder...
copy /y "dist\Rexdesk Version Manager.exe" "C:\Users\Influ\Documents\Rexdesk Vershons\Rexdesk Version Manager.exe"
if %errorlevel% neq 0 (
    echo.
    echo Copy failed.
    pause
    exit /b 1
)
echo.
echo Done! EXE updated at: C:\Users\Influ\Documents\Rexdesk Vershons\Rexdesk Version Manager.exe
pause
