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
  goto :done
) else (
  echo.
  echo Push finished OK.
)

echo.
set "CREATE_RELEASE="
set /p CREATE_RELEASE=Create or update a GitHub release now? (y/N): 
if /i not "%CREATE_RELEASE%"=="y" goto :done

where gh >nul 2>&1
if errorlevel 1 (
  echo GitHub CLI ^(gh^) is not installed.
  echo Install from: https://cli.github.com/
  goto :done
)

gh auth status >nul 2>&1
if errorlevel 1 (
  echo You are not logged in to GitHub CLI.
  echo Run: gh auth login
  goto :done
)

set "TAG_NAME="
set /p TAG_NAME=Enter release tag (example v1.0.0): 
if "%TAG_NAME%"=="" (
  echo No tag entered. Skipping release step.
  goto :done
)

git rev-parse "%TAG_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Creating and pushing tag %TAG_NAME%...
  git tag "%TAG_NAME%"
  if errorlevel 1 (
    echo Failed to create tag.
    goto :done
  )
  git push origin "%TAG_NAME%"
  if errorlevel 1 (
    echo Failed to push tag.
    goto :done
  )
) else (
  echo Tag %TAG_NAME% already exists locally.
  git ls-remote --tags origin "%TAG_NAME%" >nul 2>&1
  if errorlevel 1 (
    echo Pushing existing local tag %TAG_NAME%...
    git push origin "%TAG_NAME%"
    if errorlevel 1 (
      echo Failed to push existing tag.
      goto :done
    )
  )
)

set "NOTES_FILE=%TEMP%\rexdesk_release_notes_%RANDOM%.md"
(
  echo ## Patch Notes
  echo.
  echo - Replace this line with your patch notes.
  echo.
  echo ## Install
  echo.
  echo - Download and run `Rexdesk-Version-Manager-Setup.exe`.
) > "%NOTES_FILE%"

echo Opening patch notes editor...
start /wait notepad "%NOTES_FILE%"

gh release view "%TAG_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Creating GitHub release %TAG_NAME%...
  gh release create "%TAG_NAME%" --title "%TAG_NAME%" --notes-file "%NOTES_FILE%"
  if errorlevel 1 (
    echo Failed to create release.
    del /q "%NOTES_FILE%" >nul 2>&1
    goto :done
  )
) else (
  echo Updating existing GitHub release %TAG_NAME%...
  gh release edit "%TAG_NAME%" --title "%TAG_NAME%" --notes-file "%NOTES_FILE%"
  if errorlevel 1 (
    echo Failed to update release.
    del /q "%NOTES_FILE%" >nul 2>&1
    goto :done
  )
)

echo Release notes published for %TAG_NAME%.
del /q "%NOTES_FILE%" >nul 2>&1

:done
echo.
pause
