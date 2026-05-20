@echo off
echo ========================================
echo   Protocol Editor - Setup & Launch
echo ========================================
echo.

:: Check Python
echo [1/3] Checking Python ...
python --version 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Python not found!
    echo Please install Python 3.10+ from:
    echo   https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
echo [OK] Python found.

:: Install dependencies
echo.
echo [2/3] Installing dependencies ...
pip install PySide6 python-docx
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies ready.

:: Run
echo.
echo [3/3] Launching editor ...
cd /d "%~dp0"
start "Protocol Editor" pythonw main.py
if errorlevel 1 (
    python main.py
)
exit
