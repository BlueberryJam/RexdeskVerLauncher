@echo off
setlocal
cd /d "%~dp0"
title Git Pull — Rexdesk Vershons
echo Repository: %CD%
echo.
git pull
if errorlevel 1 (
  echo.
  echo Pull finished with errors ^(see messages above^).
) else (
  echo.
  echo Pull finished OK.
)
echo.
pause
