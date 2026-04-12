@echo off
echo ============================================
echo  TrackMind — Build Installer
echo ============================================
echo.

if not exist "dist\Trackmind" (
    echo ERROR: dist\Trackmind.exe not found.
    echo Run BUILD_EXE.bat first, then run this script.
    pause
    exit /b 1
)

set MAKENSIS=C:\Program Files (x86)\NSIS\makensis.exe

echo Building installer...
echo.

"%MAKENSIS%" installer.nsi

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  INSTALLER COMPLETE
echo  Output: Trackmind.exe
echo ============================================
echo.
pause
