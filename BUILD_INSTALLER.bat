@echo off
echo ============================================
echo  TrackMind - Build Installer
echo ============================================
echo.

if not exist "dist\Trackmind.exe" (
    echo ERROR: dist\Trackmind.exe not found.
    echo Run BUILD_EXE.bat first, then run this script.
    pause
    exit /b 1
)

if not exist "version.txt" (
    echo ERROR: version.txt not found.
    pause
    exit /b 1
)

rem Read version from version.txt and strip leading 'v' or 'V'
set /p VER_RAW=<version.txt
set VER=%VER_RAW%
if /i "%VER_RAW:~0,1%"=="v" set VER=%VER_RAW:~1%

rem Build 4-part version for Windows PE metadata (e.g. 1.1 -> 1.1.0.0)
set VER4=%VER%.0.0.0
for /f "tokens=1-4 delims=." %%a in ("%VER4%") do set VER4=%%a.%%b.%%c.%%d

echo Version : %VER%
echo PE Ver  : %VER4%
echo.

set MAKENSIS=C:\Program Files (x86)\NSIS\makensis.exe

echo Building installer...
echo.

"%MAKENSIS%" /DAPP_VERSION=%VER% /DAPP_VERSION_4=%VER4% installer.nsi

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  INSTALLER COMPLETE: Trackmind_Setup.exe
echo  Version: %VER%
echo ============================================
echo.
pause
