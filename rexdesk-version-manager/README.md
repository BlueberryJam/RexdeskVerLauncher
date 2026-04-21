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

From PowerShell in this folder:

```powershell
python .\main.py
```

Or use helper script:

```powershell
.\run-manager.ps1
```

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
