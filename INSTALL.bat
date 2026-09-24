@echo off
echo ============================================
echo  Trackmind - First-Time Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Download Python 3.9-3.11 from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo Installing required Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Package install failed. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo  Double-click START_TRACKER.bat to run Trackmind.
echo  The first launch walks you through camera setup.
echo ============================================
pause
