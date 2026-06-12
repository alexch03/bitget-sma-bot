#!/usr/bin/env bash
# Setup script for Linux/Mac. Creates venv, installs deps, copies .env.example.
# Make executable first: chmod +x install.sh
set -euo pipefail

cd "$(dirname "$0")"

# Find a suitable python (prefer 3.11+)
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        VER=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
        MAJOR=${VER%%.*}
        MINOR=${VER##*.}
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.11+ is required but was not found on PATH."
    echo "Install it from https://www.python.org/downloads/ or via your package manager."
    exit 1
fi

echo "Using $($PYTHON --version) at $(command -v $PYTHON)"

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv .venv
else
    echo "Virtual environment already exists."
fi

# Activate and install
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing requirements..."
python -m pip install -r requirements.txt

# Copy .env.example -> .env if missing
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env from .env.example."
    else
        echo "Warning: .env.example not found, skipping .env copy."
    fi
else
    echo ".env already exists, leaving it alone."
fi

echo
echo "Setup complete. Edit .env with your Bitget keys, then run ./start.sh"
