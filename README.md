# RexdeskVerLauncher

So you can have multiple versions of Rexdesk installed on a PC for testing.

Version data is stored under `library/` in this folder. New releases are
discovered and downloaded directly from the Influx download server, so there is
no longer a bundled executable to keep in sync.

## Quick Start

Double-click `Install-and-Run.bat`.

That script creates a local Python virtual environment, installs dependencies,
and launches the app. To start it again later without re-running setup, use
`Launch Rexdesk Version Manager.bat`.

## Project Docs

Full documentation is in:

- `rexdesk-version-manager/README.md`
