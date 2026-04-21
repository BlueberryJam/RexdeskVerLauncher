@echo off
setlocal
cd /d "%~dp0"
title Git Push — Rexdesk Vershons
echo Repository: %CD%
echo.

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo This folder is not a Git repository.
  goto :done
)

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Sync local changes"
  if errorlevel 1 (
    echo Commit failed ^(see messages above^). Push not attempted.
    goto :done
  )
  echo Committed your changes.
) else (
  echo Nothing new to commit.
)

git push
if errorlevel 1 (
  echo.
  echo Push finished with errors ^(see messages above^).
) else (
  echo.
  echo Push finished OK.
)

:done
echo.
pause
