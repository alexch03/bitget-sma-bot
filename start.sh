#!/usr/bin/env bash
# Start the trading bot.
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
echo "Starting bot. Press Ctrl+C to stop."
exec python -m src.main
