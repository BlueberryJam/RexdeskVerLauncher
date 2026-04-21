param(
    [switch]$InstallDragDrop
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if ($InstallDragDrop) {
    python -m pip install tkinterdnd2
}

python ".\main.py"
