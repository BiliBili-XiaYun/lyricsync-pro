#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venv = Join-Path $root '.venv'
if (!(Test-Path $venv)) {
    Write-Host "Creating virtual environment at $venv"
    python -m venv $venv
}

# Activate venv
& "$venv\Scripts\Activate.ps1"

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Build with PyInstaller in onefile mode
$pyiArgs = @(
    '--noconfirm',
    '--clean',
    '--onefile',
    '--windowed',
    '--name','LyricSyncPro',
    '--log-level','WARN',
    '--collect-all','PySide6'
)

# Entry point
$entry = 'main.py'

Write-Host "Running: pyinstaller $($pyiArgs -join ' ') $entry"
pyinstaller @pyiArgs $entry

$exe = Join-Path $root 'dist/LyricSyncPro.exe'
if (Test-Path $exe) {
    $sizeMB = [Math]::Round((Get-Item $exe).Length / 1MB, 2)
    Write-Host "Build succeeded: $exe ($sizeMB MB)" -ForegroundColor Green
} else {
    Write-Error "Build failed: executable not found at $exe"
    exit 1
}
