@echo off
REM Setup script for Windows. Creates venv, installs deps, copies .env.example.
setlocal

echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Verify version is 3.11 or higher
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)
if %PYMAJOR% LSS 3 (
    echo Found Python %PYVER%. Need 3.11 or newer.
    pause
    exit /b 1
)
if %PYMAJOR% EQU 3 if %PYMINOR% LSS 11 (
    echo Found Python %PYVER%. Need 3.11 or newer.
    pause
    exit /b 1
)
echo Python %PYVER% OK.

REM Create venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

REM Activate venv and install
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Could not activate venv.
    pause
    exit /b 1
)

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

REM Copy .env.example -> .env if missing
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo Created .env from .env.example.
    ) else (
        echo Warning: .env.example not found, skipping .env copy.
    )
) else (
    echo .env already exists, leaving it alone.
)

echo.
echo Setup complete. Edit .env with your Bitget keys, then run start.bat
echo.
pause
endlocal
