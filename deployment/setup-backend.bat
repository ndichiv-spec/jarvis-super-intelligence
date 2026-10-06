@echo off
REM JARVIS Backend Setup Script for Windows
REM Run this to set up the backend quickly

echo ========================================
echo   JARVIS Backend Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org
    pause
    exit /b 1
)

echo [1/6] Python found!
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [2/6] Creating virtual environment...
    python -m venv venv
) else (
    echo [2/6] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [4/6] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt
echo.

REM Create necessary directories
echo [5/6] Creating necessary directories...
if not exist "logs" mkdir logs
if not exist "data" mkdir data
echo.

REM Copy .env.example if .env doesn't exist
if not exist ".env" (
    echo [6/6] Creating .env from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit .env with your configuration before starting!
    echo.
) else (
    echo [6/6] .env file already exists
)
echo.

echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Edit .env with your configuration (optional)
echo 2. Start the server: uvicorn api.main:app --reload --port 8000
echo 3. Open browser: http://localhost:8000/api/v1/docs
echo.
echo For detailed setup instructions, see BACKEND_SETUP.md
echo.
pause
