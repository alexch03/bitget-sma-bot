# Install guide

[🇬🇧 English](INSTALL.md) | [🇫🇷 Français](INSTALL.fr.md)

Quick setup for the Bitget SMA bot. Read [DISCLAIMER.md](DISCLAIMER.md) before running anything with real money.

## Requirements

- Python 3.11 or newer
- A Bitget account with API keys (only for `demo` and `live` modes)

## Windows

1. Double-click **`install.bat`** and wait for it to finish.
2. Open **`.env`** in a text editor and paste your Bitget API keys.
3. Double-click **`start.bat`** to run the bot, or **`start_web.bat`** to open the dashboard at http://localhost:5000.
4. **`stop.bat`** kills any running bot/web process.

## Linux / macOS

```bash
chmod +x *.sh
./install.sh
# edit .env with your Bitget keys
./start.sh           # or ./start_web.sh
./stop.sh            # to stop
```

That's it. If something breaks, re-run `install.bat` / `install.sh` to repair the venv.
