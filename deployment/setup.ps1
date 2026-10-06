# Setup script for Windows (PowerShell)
# Creates a virtual environment, activates it, upgrades pip, and installs requirements

$venv = ".venv"
if (-Not (Test-Path $venv)) {
    python -m venv $venv
}

Write-Host "Activating virtual environment..."
$activate = Join-Path $venv "Scripts\Activate.ps1"
if (Test-Path $activate) {
    & $activate
} else {
    Write-Host "Could not find activation script at $activate. Activate the venv manually: .\.venv\Scripts\Activate.ps1"
}

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing requirements from requirements.txt..."
try {
    python -m pip install -r requirements.txt
    Write-Host "Requirements installed."
} catch {
    Write-Host "pip install failed: $_"
    Write-Host "If pyaudio or pocketsphinx fail to build, consider installing prebuilt wheels or the relevant system packages."
}

Write-Host "Setup complete. If audio drivers are missing, follow README.md troubleshooting notes."
