# Rexdesk Version Manager

Windows desktop app for keeping Rexdesk MSI versions archived, tracked, and launchable from one UI.

## What it does now

- Shows version list with `Version`, `Status`, `Installed Path`, and `MSI Saved`.
- Keeps a local catalog at `library/catalog.json`.
- Stores every imported MSI under `library/msi/`.
- Loads and saves per-version patch notes in `library/patch_notes/<version>.txt`.
- Supports actions for selected version:
  - `Install`, `Uninstall`, `Reinstall`
  - `Launch`, `Open Install Folder`
  - `Reveal MSI`, `Copy MSI Path`, `Export MSI Copy`
- Drag-and-drop MSI support when `tkinterdnd2` is installed.

## Folder layout

Generated automatically:

- `library/msi/`
- `library/installs/<version>/`
- `library/patch_notes/<version>.txt`
- `library/catalog.json`

## Run

### Easiest (one-click, recommended)

Double-click:

`Install-and-Run.bat`

This script will:

- create a local `.venv` virtual environment
- install required dependencies from `requirements.txt`
- install optional drag-and-drop support (`tkinterdnd2`)
- launch the app

### PowerShell

From PowerShell in this folder:

```powershell
python .\main.py
```

Or use helper script:

```powershell
.\run-manager.ps1
```

## Build for end users (no Python required)

If you want to share this app with users who do not have Python installed:

1. Build portable EXE

   - Run `build.bat`
   - Output: `release/Rexdesk Version Manager.exe`

2. Build Windows installer (recommended)

   - Install Inno Setup 6: https://jrsoftware.org/isinfo.php
   - Run `build-installer.bat`
   - Output: `release/Rexdesk-Version-Manager-Setup.exe`

Users can then install by double-clicking the setup EXE.

## Super-easy GitHub release flow

You can have GitHub build and publish the installer automatically.

### Option A: One-click manual build

1. Open GitHub repo `Actions` tab.
2. Run workflow: `Build Windows Release`.
3. Download artifacts from the workflow run:
   - `Rexdesk Version Manager.exe`
   - `Rexdesk-Version-Manager-Setup.exe`

### Option B: Auto-publish on version tag (recommended)

1. Create and push a tag like `v1.0.0`.
2. GitHub Actions builds both files.
3. GitHub automatically creates/updates a Release and attaches:
   - `Rexdesk Version Manager.exe`
   - `Rexdesk-Version-Manager-Setup.exe`

Tag commands:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

End users then just download the installer from the repo Releases page.

### Auto release notes

- A draft release is now auto-maintained from merged PR titles.
- On each `v*` tag, GitHub auto-generates release notes and publishes installer assets.
- Use PR labels like `feature`, `enhancement`, `fix`, `bug`, `docs`, `chore`, `ci` for cleaner changelog sections.

## Enable drag-and-drop MSI import

Install optional dependency:

```powershell
python -m pip install tkinterdnd2
```

Then run again. You can also do this with:

```powershell
.\run-manager.ps1 -InstallDragDrop
```

## Notes

- MSI side-by-side behavior depends on how each package was authored.
- If install fails due to MSI coexistence restrictions, the app preserves the MSI for reinstall-on-demand workflows.
