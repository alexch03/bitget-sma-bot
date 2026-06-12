#!/usr/bin/env bash
# Start the Flask web UI on port 5000.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run ./install.sh first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo ".env file not found. Run ./install.sh first, then edit .env with your Bitget keys."
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "Starting web UI on http://localhost:5000 . Press Ctrl+C to stop."
exec python -m src.web
