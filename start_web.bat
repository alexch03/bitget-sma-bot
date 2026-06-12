@echo off
REM Start the Flask web UI on port 5000.
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo .env file not found. Run install.bat first, then edit .env with your Bitget keys.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo Starting web UI on http://localhost:5000 . Press Ctrl+C to stop.
python -m src.web

endlocal
