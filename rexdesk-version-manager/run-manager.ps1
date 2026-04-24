param(
    [switch]$InstallDragDrop
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating local virtual environment (.venv)..."
    python -m venv .venv
}

$pythonExe = ".\.venv\Scripts\python.exe"

Write-Host "Ensuring required dependencies are installed..."
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r ".\requirements.txt"

if ($InstallDragDrop) {
    Write-Host "Installing optional drag-and-drop dependency..."
    & $pythonExe -m pip install tkinterdnd2
}

Write-Host "Launching Rexdesk Version Manager..."
& $pythonExe ".\main.py"
