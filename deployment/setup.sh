#!/usr/bin/env bash
# Cross-platform setup script (Linux/macOS). Creates venv and installs requirements.
set -e
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
. "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || {
  echo "pip install failed. If audio packages fail, install system packages or see README.md.";
}

echo "Setup complete. Activate with: source $VENV_DIR/bin/activate"
