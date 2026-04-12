@echo off
echo ============================================
echo  PTZ Auto-Tracker - First-Time Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Download Python 3.10+ from https://www.python.org/downloads/
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
echo  Edit START_TRACKER.bat with your camera IP,
echo  then double-click it to run.
echo ============================================
pause
