@echo off
setlocal
cd /d "%~dp0"

call ".\build.bat"
if %errorlevel% neq 0 (
    echo Portable build failed, installer was not created.
    exit /b 1
)

if not exist "release\Rexdesk Version Manager.exe" (
    echo Expected EXE not found at release\Rexdesk Version Manager.exe
    exit /b 1
)

set "ISCC_EXE="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC_EXE%"=="" (
    echo Inno Setup 6 was not found.
    echo Install it from:
    echo https://jrsoftware.org/isinfo.php
    echo Then run this script again to generate a setup installer.
    pause
    exit /b 1
)

echo Building installer with Inno Setup...
"%ISCC_EXE%" "installer.iss"
if %errorlevel% neq 0 (
    echo Installer build failed.
    pause
    exit /b 1
)

echo.
echo Installer created in:
echo %cd%\release\Rexdesk-Version-Manager-Setup.exe
pause
